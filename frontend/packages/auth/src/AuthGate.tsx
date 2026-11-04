import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { ApiError, auth, installAuth, tokenStore, type Contact, type Principal } from "@saathi/api-client";

/**
 * Nothing in an app shows until the server says who is looking.
 *
 * When the server says login is off (the demo, where the stage frames every role
 * at once) the gate opens straight away and `principal` is null; an app reads it
 * and falls back to its demo persona. When login is on, the gate shows the right
 * way in for the app (a password for staff, a phone and a code for a family),
 * and refuses a person signed in as the wrong role instead of showing them a
 * screen full of errors.
 */

interface SessionValue {
  /** Null when login is off. */
  principal: Principal | null;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue>({ principal: null, signOut: () => undefined });

export const useSession = (): SessionValue => useContext(SessionContext);

type State =
  | { kind: "loading" }
  | { kind: "offline"; message: string }
  | { kind: "open" }
  | { kind: "signedOut" }
  | { kind: "ready"; principal: Principal };

export interface AuthGateProps {
  /** The app's name, for the sign-in page. */
  app: string;
  /** Staff sign in with a password; a family with a phone number and a code. */
  way: "staff" | "family";
  /** Who may use this app. Anyone else is told so. */
  roles: Principal["role"][];
  children: ReactNode;
}

export function AuthGate({ app, way, roles, children }: AuthGateProps) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const start = useCallback(async () => {
    setState({ kind: "loading" });
    installAuth(() => setState({ kind: "signedOut" }));
    try {
      const config = await auth.config();
      if (!config.required) {
        // A token left from a session against a world with login on means nothing
        // here, and would make the stream ask for tickets this server does not issue.
        tokenStore.clear();
        return setState({ kind: "open" });
      }
      if (!tokenStore.get()) return setState({ kind: "signedOut" });
      const principal = await auth.me().catch(() => null);
      if (principal) setState({ kind: "ready", principal });
      else {
        tokenStore.clear();
        setState({ kind: "signedOut" });
      }
    } catch (e) {
      setState({
        kind: "offline",
        message: e instanceof Error ? e.message : "could not reach the server",
      });
    }
  }, []);

  useEffect(() => {
    void start();
  }, [start]);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setState({ kind: "signedOut" });
  }, []);

  const value = useMemo<SessionValue>(
    () => ({ principal: state.kind === "ready" ? state.principal : null, signOut }),
    [state, signOut],
  );

  if (state.kind === "loading") return <Page app={app}>Opening…</Page>;
  if (state.kind === "offline") {
    return (
      <Page app={app}>
        <p>The server did not answer.</p>
        <p className="auth-small">{state.message}</p>
        <button type="button" className="auth-btn" onClick={() => void start()}>
          Try again
        </button>
      </Page>
    );
  }
  if (state.kind === "signedOut") {
    return (
      <Page app={app}>
        {way === "staff" ? (
          <StaffSignIn onSignedIn={(principal) => setState({ kind: "ready", principal })} />
        ) : (
          <FamilySignIn onSignedIn={(principal) => setState({ kind: "ready", principal })} />
        )}
      </Page>
    );
  }
  if (state.kind === "ready" && !roles.includes(state.principal.role)) {
    return (
      <Page app={app}>
        <p>
          You are signed in as <strong>{state.principal.name}</strong> ({state.principal.role}),
          and this screen is not for that role.
        </p>
        <button type="button" className="auth-btn" onClick={signOut}>
          Sign out
        </button>
      </Page>
    );
  }
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

function Page({ app, children }: { app: string; children: ReactNode }) {
  return (
    <div className="auth-page">
      <main className="auth-card">
        <h1>
          Saathi <span>{app}</span>
        </h1>
        {children}
      </main>
    </div>
  );
}

const reason = (e: unknown, fallback: string): string => {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string" && (e.status === 429 || e.status === 401)) return e.detail;
    if (e.status === 401) return fallback;
  }
  return "Something went wrong. Try again.";
};

function StaffSignIn({ onSignedIn }: { onSignedIn: (p: Principal) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await auth.login(username.trim(), password);
      tokenStore.set(session.token);
      onSignedIn(session.principal);
    } catch (e) {
      setError(reason(e, "Wrong username or password."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <label>
        Username
        <input
          autoFocus
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </label>
      <label>
        Password
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <button className="auth-btn primary" disabled={busy || !username || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

function FamilySignIn({ onSignedIn }: { onSignedIn: (p: Principal) => void }) {
  // Email first: it works without an SMS provider and costs the family nothing.
  const [by, setBy] = useState<"email" | "phone">("email");
  const [value, setValue] = useState("");
  const [code, setCode] = useState("");
  const [asked, setAsked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const contact = (): Contact =>
    by === "email" ? { email: value.trim().toLowerCase() } : { phone: value.trim() };
  const looksRight = by === "email" ? /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim()) : value.trim().length >= 5;

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.requestOtp(contact());
      setAsked(true);
    } catch {
      setError(`Could not send a code. Check the ${by === "email" ? "email address" : "number"} and try again.`);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await auth.verifyOtp(contact(), code.trim());
      tokenStore.set(session.token);
      onSignedIn(session.principal);
    } catch (e) {
      setError(reason(e, "That code is wrong or has expired."));
    } finally {
      setBusy(false);
    }
  };

  const switchTo = (next: "email" | "phone") => {
    setBy(next);
    setValue("");
    setError(null);
  };

  if (!asked) {
    return (
      <form onSubmit={ask}>
        <label>
          {by === "email" ? "Your email address" : "Your phone number"}
          <input
            key={by}
            autoFocus
            type={by === "email" ? "email" : "tel"}
            inputMode={by === "email" ? "email" : "tel"}
            autoComplete={by === "email" ? "email" : "tel"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <p className="auth-small">
          We send a code to the {by === "email" ? "email address" : "number"} the hospital has for you. If it
          is on record, it arrives{by === "email" ? " (look in spam too)" : ""}.
        </p>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="auth-btn primary" disabled={busy || !looksRight}>
          Send me a code
        </button>
        <button type="button" className="auth-btn" onClick={() => switchTo(by === "email" ? "phone" : "email")}>
          {by === "email" ? "Use my phone number instead" : "Use my email address instead"}
        </button>
      </form>
    );
  }
  return (
    <form onSubmit={verify}>
      <label>
        The code we sent
        <input
          autoFocus
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
      </label>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <button className="auth-btn primary" disabled={busy || code.trim().length < 4}>
        {busy ? "Checking…" : "Continue"}
      </button>
      <button
        type="button"
        className="auth-btn"
        onClick={() => {
          setAsked(false);
          setCode("");
          setError(null);
        }}
      >
        Use a different {by === "email" ? "address" : "number"}
      </button>
    </form>
  );
}
