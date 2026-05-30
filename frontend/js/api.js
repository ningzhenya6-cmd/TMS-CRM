/**
 * API 客户端 — 封装 fetch，自动处理 JWT 和错误
 */
const API = (() => {
  const BASE = '/api';

  function getToken() {
    return localStorage.getItem('tms_token') || '';
  }

  async function request(method, path, body = null) {
    const url = BASE + path;
    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    try {
      const res = await fetch(url, opts);
      const data = await res.json();

      if (!res.ok) {
        // 401 — 自动退出
        if (res.status === 401) {
          localStorage.removeItem('tms_token');
          localStorage.removeItem('tms_user');
          window.location.reload();
        }
        return { error: data.error || '请求失败 (' + res.status + ')' };
      }
      return data.data !== undefined ? data : { data };
    } catch (e) {
      return { error: '网络连接失败，请检查网络' };
    }
  }

  async function requestRaw(method, path) {
    const url = BASE + path;
    const headers = {};
    const token = getToken();
    if (token) headers['Authorization'] = 'Bearer ' + token;

    try {
      const res = await fetch(url, { method, headers });
      if (!res.ok) return null;
      return await res.blob();
    } catch (e) {
      return null;
    }
  }

  return {
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body),
    put: (path, body) => request('PUT', path, body),
    del: (path, body) => request('DELETE', path, body),
    getRaw: (path) => requestRaw('GET', path),
  };
})();
