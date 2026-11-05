import { test } from 'node:test'
import assert from 'node:assert/strict'
import { authErrorMessage } from './authErrors.js'

const failure = (status, detail) => ({ response: { status, data: { detail } } })

test('shows missing users, wrong passwords and registered usernames', () => {
  assert.match(authErrorMessage(failure(401, '工号不存在')), /用户不存在/)
  assert.match(authErrorMessage(failure(401, '学校和工号不匹配')), /学校、工号/)
  assert.equal(authErrorMessage(failure(401, '密码错误')), '密码错误')
  assert.match(authErrorMessage(failure(409, '工号已被使用'), 'register'), /已被注册/)
  assert.match(authErrorMessage(failure(409, '该学校的工号已被使用'), 'register'), /该学校的工号已被注册/)
})

test('shows actionable invitation and password errors', () => {
  for (const detail of ['邀请码不正确', '两次输入的密码不一致', '密码至少 8 位', '当前未开放注册']) {
    assert.equal(authErrorMessage(failure(400, detail), 'register'), detail)
  }
})

test('handles validation, rate limits, network, timeout and server failures', () => {
  assert.match(authErrorMessage(failure(422, [{ msg: 'invalid' }])), /格式不正确/)
  assert.match(authErrorMessage(failure(429)), /次数过多/)
  assert.match(authErrorMessage({}), /检查网络/)
  assert.match(authErrorMessage({ code: 'ECONNABORTED' }), /超时/)
  assert.match(authErrorMessage(failure(500, 'internal private detail')), /服务暂时不可用/)
})
