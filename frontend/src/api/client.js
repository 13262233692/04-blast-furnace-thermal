const BASE = '/api'

async function getJson(url, options) {
  const resp = await fetch(url, options)
  if (!resp.ok) {
    throw new Error('请求失败 ' + resp.status + ': ' + url)
  }
  return resp.json()
}

export function fetchField(level, since = 0) {
  return getJson(BASE + '/inversion/field?level=' + level + '&since=' + since)
}

export function fetchOverview() {
  return getJson(BASE + '/inversion/overview')
}

export function updateRegParams(regLambda, regMu) {
  return getJson(BASE + '/inversion/params', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reg_lambda: regLambda, reg_mu: regMu }),
  })
}
