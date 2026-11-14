
const API = import.meta.env.VITE_API_URL || "http://localhost:8000"

async function request(path, options) {
  const res = await fetch(`${API}${path}`, options)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { detail = (await res.json()).detail || detail } catch (_) {}
    throw new Error(detail)
  }
  return res.json()
}

export function uploadFile(file) {
  const form = new FormData()
  form.append("file", file)
  return request("/upload", { method: "POST", body: form })
}

export function getStatus(job_id) {
  return request(`/status/${job_id}`)
}
