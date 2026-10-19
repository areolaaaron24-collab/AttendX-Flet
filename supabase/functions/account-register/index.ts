import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: Record<string, unknown>, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { ...cors, "Content-Type": "application/json" },
});
const norm = (v: unknown) => String(v ?? "").trim().replace(/\s+/g, " ");
const noDigits = (v: string) => !/\d/.test(v);

async function sha256hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Method not allowed." }, 405);
  const url = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !anonKey || !serviceKey) return json({ error: "Server authentication is not configured." }, 503);
  try {
    const raw = await req.json();
    const accountId = norm(raw.accountId).toLowerCase();
    const role = norm(raw.role).toUpperCase();
    const password = String(raw.password ?? "");
    const firstName = norm(raw.firstName);
    const lastName = norm(raw.lastName);
    const middleName = norm(raw.middleName);
    const suffix = norm(raw.suffix);
    const sex = norm(raw.sex);
    const recoveryEmail = norm(raw.recoveryEmail).toLowerCase();
    const course = norm(raw.course);
    const yearLevel = norm(raw.yearLevel);
    const section = norm(raw.section);
    const department = norm(raw.department);
    const office = norm(raw.office);
    if (!/^[a-z0-9][a-z0-9._-]{0,63}$/.test(accountId)) return json({ error: "Account ID format is invalid." }, 400);
    if (role !== "TEACHER" && role !== "STUDENT") return json({ error: "Only Teacher and Student accounts are allowed." }, 400);
    if (password.length < 8 || password.length > 128) return json({ error: "Password must be 8–128 characters." }, 400);
    if (!firstName || !lastName || !noDigits(firstName) || !noDigits(lastName) || !noDigits(middleName) || !noDigits(suffix)) {
      return json({ error: "First and Last Name are required; name fields must not contain numbers." }, 400);
    }
    if (sex !== "Male" && sex !== "Female") return json({ error: "Sex must be Male or Female." }, 400);
    if (recoveryEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recoveryEmail)) return json({ error: "Recovery email is invalid." }, 400);
    if (role === "STUDENT" && (!course || !yearLevel || !section)) return json({ error: "Course, Year, and Section are required for students." }, 400);

    const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: existing, error: lookupError } = await admin.from("profiles").select("id").eq("account_id", accountId).maybeSingle();
    if (lookupError) return json({ error: "Account registry is unavailable. Check the database migration." }, 503);
    if (existing) return json({ error: "That Account ID is already registered. Account IDs are unique across both portals." }, 409);

    const authEmail = recoveryEmail || `acct-${await sha256hex(`${role}|${accountId}`)}@login.attendx.invalid`;
    const { data: created, error: createError } = await admin.auth.admin.createUser({
      email: authEmail,
      password,
      email_confirm: true,
      user_metadata: {
        account_id: accountId, role, first_name: firstName, last_name: lastName,
        middle_name: middleName, suffix, sex, recovery_email: recoveryEmail || null,
        course: role === "STUDENT" ? course : null,
        year_level: role === "STUDENT" ? yearLevel : null,
        section: role === "STUDENT" ? section : null,
        department: role === "TEACHER" ? department || null : null,
        office: role === "TEACHER" ? office || null : null,
      },
    });
    if (createError || !created.user) {
      const message = createError?.message ?? "Account creation failed.";
      if (/already|duplicate|unique/i.test(message)) return json({ error: "That Account ID or recovery email is already registered." }, 409);
      return json({ error: "Account could not be created. Check Auth settings and the profile trigger." }, 400);
    }

    const authClient = createClient(url, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: signedIn, error: signInError } = await authClient.auth.signInWithPassword({ email: authEmail, password });
    if (signInError || !signedIn.session) return json({ error: "Account was created but automatic sign-in failed. Please sign in from the portal." }, 200);
    return json({ session: signedIn.session, user: signedIn.user, message: "Account created." }, 201);
  } catch (_error) {
    return json({ error: "Registration request could not be processed." }, 400);
  }
});
