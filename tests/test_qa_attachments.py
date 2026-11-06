from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import PropertyMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from ai_engine.config import Settings
from ai_engine.providers.base import ProviderError
from ai_engine.qa.pipeline import _assemble_contexts, _build_messages
from backend.app.api.qa import (
    _attachment_contexts,
    _eval_history_items,
    _format_eval_context,
    _public_contexts,
)
from backend.app.core import qa_attachments
from backend.app.schemas import QAForm

# 1×1 PNG
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class QAAttachmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(
            qa_attachments,
            "_user_root",
            side_effect=lambda user_id: self.root / user_id,
        )
        self.root_patch.start()

    def tearDown(self) -> None:
        self.root_patch.stop()
        self.temp.cleanup()

    def test_text_attachment_is_private_loadable_and_deletable(self):
        item = qa_attachments.save_attachment(
            user_id="teacher-a",
            original_name="学生作业.txt",
            content="第一组：概念理解有误。\n第二组：计算步骤不完整。".encode(),
            content_type="text/plain",
        )
        self.assertEqual(item["status"], "ready")
        self.assertIn("第一组", item["preview"])
        self.assertIsNotNone(qa_attachments.load_attachment("teacher-a", item["id"]))
        self.assertIsNone(qa_attachments.load_attachment("teacher-b", item["id"]))
        self.assertTrue(qa_attachments.delete_attachment("teacher-a", item["id"]))
        self.assertIsNone(qa_attachments.load_attachment("teacher-a", item["id"]))

    def test_unsupported_file_does_not_leave_directory(self):
        with self.assertRaisesRegex(ValueError, "不支持"):
            qa_attachments.save_attachment(
                user_id="teacher-a",
                original_name="notes.bmp",
                content=b"not-an-image",
            )
        self.assertFalse((self.root / "teacher-a").exists())

    def test_png_is_stored_as_image_without_text_extraction(self):
        item = qa_attachments.save_attachment(
            user_id="teacher-a",
            original_name="课堂板书.png",
            content=_PNG,
            content_type="application/octet-stream",
        )
        self.assertEqual(item["kind"], "image")
        self.assertEqual(item["content_type"], "image/png")
        self.assertEqual(item["char_count"], 0)
        loaded = qa_attachments.load_attachment("teacher-a", item["id"])
        self.assertIsNotNone(loaded)
        metadata, text = loaded
        self.assertEqual(metadata["kind"], "image")
        self.assertEqual(text, "")
        self.assertTrue(qa_attachments.original_path("teacher-a", item["id"]).is_file())

    def test_image_bytes_must_match_suffix(self):
        with self.assertRaisesRegex(ValueError, "图片内容"):
            qa_attachments.save_attachment(
                user_id="teacher-a",
                original_name="photo.png",
                content=b"\xff\xd8\xffnot-a-png",
            )
        self.assertFalse((self.root / "teacher-a").exists())

    def test_image_context_inlines_pixels_and_keeps_them_out_of_prompt_text(self):
        item = qa_attachments.save_attachment(
            user_id="teacher-a",
            original_name="课堂板书.png",
            content=_PNG,
        )
        with patch.object(Settings, "mode", new_callable=PropertyMock, return_value="cloud"):
            contexts, history = _attachment_contexts("teacher-a", [item["id"]])
            messages = _build_messages("这张板书在讲什么", contexts, [], "ask")
        self.assertEqual(history[0]["kind"], "image")
        self.assertTrue(contexts[0]["image_data_url"].startswith("data:image/png;base64,"))
        self.assertNotIn("data:image", contexts[0]["text"])
        content = messages[1].content
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "text")
        self.assertIn("【上传文件】课堂板书.png", content[0]["text"])
        self.assertIn("禁止", content[0]["text"])
        self.assertNotIn(contexts[0]["image_data_url"], content[0]["text"])
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(content[1]["image_url"]["url"], contexts[0]["image_data_url"])
        self.assertIsInstance(messages[0].content, str)

    def test_local_mode_rejects_images_before_the_model_call(self):
        item = qa_attachments.save_attachment(
            user_id="teacher-a",
            original_name="课堂板书.png",
            content=_PNG,
        )
        with patch.object(Settings, "mode", new_callable=PropertyMock, return_value="local"):
            with self.assertRaises(HTTPException) as caught:
                _attachment_contexts("teacher-a", [item["id"]])
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("deepseek-flash", str(caught.exception.detail))

    def test_pipeline_rejects_images_on_local_model(self):
        context = {
            "text": "文件名：板书.png\n这是一张图片，原图附在本条消息末尾。",
            "corpus": "user_files",
            "corpus_label": "本次上传材料",
            "source": "板书.png",
            "score": 1.0,
            "pinned": True,
            "context_type": "attachment",
            "media_type": "image",
            "image_data_url": "data:image/png;base64,aaaa",
        }
        with patch.object(Settings, "mode", new_callable=PropertyMock, return_value="local"):
            with self.assertRaises(ProviderError):
                _build_messages("看这张图", [context], [], "ask")

    def test_xlsx_cells_are_extracted_without_optional_excel_engine(self):
        path = self.root / "成绩.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="班级成绩" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>姓名</t></is></c>'
                '<c r="B1" t="inlineStr"><is><t>得分</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>学生甲</t></is></c>'
                '<c r="B2"><v>82</v></c></row></sheetData></worksheet>',
            )
        text, warnings = qa_attachments.extract_text(path)
        self.assertIn("[工作表：班级成绩]", text)
        self.assertIn("A2=学生甲", text)
        self.assertIn("B2=82", text)
        self.assertEqual(warnings, [])

    def test_schema_limits_attachment_count(self):
        self.assertEqual(QAForm(question="诊断", attachment_ids=["a"]).attachment_ids, ["a"])
        with self.assertRaises(ValidationError):
            QAForm(question="诊断", attachment_ids=[str(i) for i in range(13)])

    def test_attachment_prompt_is_not_mislabeled_as_eval_report(self):
        context = {
            "text": "文件名：成绩.csv\n学生A,60",
            "corpus": "user_files",
            "corpus_label": "本次上传材料",
            "source": "成绩.csv",
            "score": 1.0,
            "pinned": True,
            "context_type": "attachment",
        }
        prompt = _build_messages(
            "诊断学生问题", [context], [], "learning_diagnosis"
        )[1].content
        self.assertIn("本次上传材料", prompt)
        self.assertIn("【上传文件】成绩.csv", prompt)
        self.assertNotIn("【指定评估】成绩.csv", prompt)

    @patch("ai_engine.qa.pipeline._retrieve_hits", return_value=[])
    def test_attachment_is_reported_separately_in_plan(self, _retrieve):
        plan = {"corpora": [], "retrieval_strategy": "chunk", "need_retrieval": False}
        contexts = _assemble_contexts(
            plan,
            user_id="teacher-a",
            eval_task_ids=None,
            pinned_contexts=[
                {
                    "text": "作业文本",
                    "corpus": "user_files",
                    "corpus_label": "本次上传材料",
                    "source": "作业.txt",
                    "score": 1.0,
                    "pinned": True,
                    "context_type": "attachment",
                }
            ],
        )
        self.assertEqual(plan["pinned_attachments"], 1)
        self.assertNotIn("pinned_eval_reports", plan)
        self.assertEqual(contexts[0]["context_type"], "attachment")

    def test_eval_report_chip_is_stored_separately_from_model_context(self):
        ctx = _format_eval_context({
            "id": "task-1",
            "filename": "课堂.mp4",
            "result": {
                "report": "需要增加提问等待",
                "overall": {"score": 86.2, "grade": "B", "grade_label": "良好"},
                "dimensions": [],
            },
        })
        chip = _eval_history_items([ctx])[0]
        self.assertEqual(chip["kind"], "eval_report")
        self.assertEqual(chip["id"], "eval:task-1")
        self.assertEqual(chip["name"], "课堂.mp4（86分）")
        public = _public_contexts([ctx])[0]
        self.assertNotIn("history_attachment", public)
        self.assertEqual(public["source"], "评估报告-课堂.mp4")
        self.assertEqual(public["context_type"], "eval_report")


if __name__ == "__main__":
    unittest.main()
