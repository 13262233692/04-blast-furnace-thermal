const BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    throw new Error(`API ${path} failed: ${resp.status}`)
  }
  return resp.json()
}

export function fetchLatestInversion(since) {
  const q = since ? `?since=${since}` : ''
  return request(`/inversion/latest${q}`)
}

export function refreshInversion(regLambda) {
  const q = regLambda ? `?reg_lambda=${regLambda}` : ''
  return request(`/inversion/refresh${q}`, { method: 'POST' })
}

export function fetchThermocouples() {
  return request('/thermocouples')
}
