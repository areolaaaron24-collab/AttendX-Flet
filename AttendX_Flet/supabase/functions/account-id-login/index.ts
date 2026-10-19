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
  try {
    const raw = await req.json();
    const accountId = String(raw.accountId ?? "").trim().toLowerCase();
    const role = String(raw.role ?? "").trim().toUpperCase();
    const password = String(raw.password ?? "");
    if (!/^[a-z0-9][a-z0-9._-]{0,63}$/.test(accountId) || !password || !["TEACHER", "STUDENT"].includes(role)) {
      return json({ error: "Invalid Account ID or password." }, 401);
    }
    const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: profile, error: profileError } = await admin.from("profiles")
      .select("id,role,is_active,student_status").eq("account_id", accountId).maybeSingle();
    if (profileError || !profile || profile.role !== role || !profile.is_active) {
      return json({ error: "Invalid Account ID or password." }, 401);
    }
    const { data: authResult, error: userError } = await admin.auth.admin.getUserById(profile.id);
    const email = authResult?.user?.email;
    if (userError || !email) return json({ error: "Invalid Account ID or password." }, 401);
    const client = createClient(url, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: signedIn, error: signInError } = await client.auth.signInWithPassword({ email, password });
    if (signInError || !signedIn.session) return json({ error: "Invalid Account ID or password." }, 401);
    return json({ session: signedIn.session, user: signedIn.user });
  } catch (_error) {
    return json({ error: "Sign-in request could not be processed." }, 400);
  }
});
