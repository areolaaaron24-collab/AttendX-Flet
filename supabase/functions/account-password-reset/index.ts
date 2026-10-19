import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: Record<string, unknown>, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { ...cors, "Content-Type": "application/json" },
});

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Method not allowed." }, 405);
  const url = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anonKey || !serviceKey) return json({ error: "Server authentication is not configured." }, 503);
  const redirect = Deno.env.get("ATTENDX_RECOVERY_REDIRECT_URL") || `${url}/functions/v1/account-password-reset-page`;
  try {
    const raw = await req.json();
    const accountId = String(raw.accountId ?? "").trim().toLowerCase();
    const role = String(raw.role ?? "").trim().toUpperCase();
    // Same generic response regardless of whether the account exists.
    if (/^[a-z0-9][a-z0-9._-]{0,63}$/.test(accountId) && ["TEACHER", "STUDENT"].includes(role)) {
      const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
      const { data: profile } = await admin.from("profiles").select("id,recovery_email,role,is_active")
        .eq("account_id", accountId).maybeSingle();
      if (profile && profile.role === role && profile.is_active && profile.recovery_email && redirect) {
        const { data: authUser } = await admin.auth.admin.getUserById(profile.id);
        const email = authUser?.user?.email;
        if (email && !email.endsWith("@login.attendx.invalid")) {
          const anon = createClient(url, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
          await anon.auth.resetPasswordForEmail(email, { redirectTo: redirect });
        }
      }
    }
    return json({ ok: true, message: "If this account has a verified recovery email, password-reset instructions will be sent." });
  } catch (_error) {
    // Keep the same external response to avoid account enumeration.
    return json({ ok: true, message: "If this account has a verified recovery email, password-reset instructions will be sent." });
  }
});
