export function authErrorMessage(error, mode) {
  const status = error.response?.status
  const detail = error.response?.data?.detail
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  if (typeof detail === 'string' && detail.trim()) {
    if (detail === '工号不存在' || detail === '学校和工号不匹配') return '用户不存在，请检查学校、工号或先注册'
    if (detail === '工号已被使用' || detail === '该学校的工号已被使用') return '该学校的工号已被注册，请直接登录或更换工号'
    return detail
  }
  if (status === 422) return '填写的信息格式不正确，请检查学校、工号、姓名和密码'
  if (status === 429) return '尝试次数过多，请稍后再试'
  if (status === 401) return '登录失败，请检查学校、工号和密码'
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return '请求超时，请稍后重试'
  if (!error.response) return '无法连接服务器，请检查网络后重试'
  return mode === 'register' ? '注册失败，请稍后重试' : '登录失败，请稍后重试'
}
