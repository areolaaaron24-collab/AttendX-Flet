const html = (url: string, anonKey: string) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AttendX Password Recovery</title>
<meta name="referrer" content="no-referrer">
<style>
:root{color-scheme:dark}body{margin:0;background:#081b34;color:#f7faff;font:16px system-ui,Segoe UI,sans-serif;min-height:100vh;display:grid;place-items:center;padding:20px;box-sizing:border-box}.panel{width:min(100%,440px);background:#102742;border:1px solid #294867;border-radius:18px;padding:28px;box-sizing:border-box}h1{margin-top:0;color:#f4c84a}label{display:block;margin:14px 0 6px;color:#aab9cc}input{width:100%;box-sizing:border-box;border-radius:10px;border:1px solid #294867;background:#081b34;color:#f7faff;padding:12px;font-size:16px}button{margin-top:18px;width:100%;border:0;border-radius:10px;background:#176aa6;color:white;padding:13px;font-weight:700;font-size:16px;cursor:pointer}p{color:#aab9cc;line-height:1.45}#status{white-space:pre-wrap;color:#39b9d7}button:disabled{opacity:.6;cursor:wait}
</style></head><body><main class="panel"><h1>AttendX</h1><h2>Set a new password</h2><p>Use this secure recovery page to update the password for the account that requested recovery. Your password is sent directly to Supabase Auth.</p>
<form id="reset-form"><label for="password">New password</label><input id="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required><label for="confirm">Confirm new password</label><input id="confirm" type="password" autocomplete="new-password" minlength="8" maxlength="128" required><button id="submit" type="submit">Update password</button></form><p id="status" role="status">Checking the secure recovery link…</p></main>
<script type="module">
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
const supabase = createClient(${JSON.stringify(url)}, ${JSON.stringify(anonKey)}, { auth: { detectSessionInUrl: true, persistSession: false, autoRefreshToken: false } });
const form = document.querySelector('#reset-form'); const status = document.querySelector('#status'); const button = document.querySelector('#submit');
let validSession = false;
try { const { data, error } = await supabase.auth.getSession(); if (error) throw error; validSession = Boolean(data.session); status.textContent = validSession ? 'Recovery link verified. Choose a new password.' : 'This recovery link is expired or invalid. Request a new reset email from AttendX.'; form.hidden = !validSession; }
catch (e) { form.hidden = true; status.textContent = 'Could not verify the recovery link. Request a new reset email.'; }
form.addEventListener('submit', async (event) => { event.preventDefault(); if (!validSession) return; const a = document.querySelector('#password').value; const b = document.querySelector('#confirm').value; if (a.length < 8 || a.length > 128) { status.textContent = 'Password must contain 8–128 characters.'; return; } if (a !== b) { status.textContent = 'The passwords do not match.'; return; } button.disabled = true; status.textContent = 'Updating password…'; try { const { error } = await supabase.auth.updateUser({ password: a }); if (error) throw error; await supabase.auth.signOut(); form.hidden = true; status.textContent = 'Password updated successfully. Return to AttendX and sign in with your Account ID and new password.'; } catch (e) { status.textContent = 'Password update failed. The link may have expired; request a new reset email.'; button.disabled = false; } });
</script></body></html>`;

Deno.serve((req) => {
  if (req.method !== "GET") return new Response("Method not allowed", { status: 405, headers: { "Allow": "GET" } });
  const url = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  if (!url || !anonKey) return new Response("Password recovery is not configured.", { status: 503 });
  return new Response(html(url, anonKey), {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
    },
  });
});
