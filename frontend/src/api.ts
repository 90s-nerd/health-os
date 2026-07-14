let csrf = document.cookie.match(/(?:^|; )health_csrf=([^;]*)/)?.[1] || "";
const ingressMatch = location.pathname.match(
  /^(.*\/api\/hassio_ingress\/[^/]+)/,
);
const appBase = ingressMatch?.[1] || "";
export const apiUrl = (path: string) => `${appBase}/api${path}`;
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}),
      ...options.headers,
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error?.message || "Something went wrong");
  if (data.csrf_token) csrf = data.csrf_token;
  return data;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
