import { useSession } from "./AuthGate";

/** What a staff screen needs to say about who is acting. */
export interface Identity<Role extends string = string> {
  name: string;
  title: string;
  role: Role;
}

/**
 * Who is acting: the person who signed in, or the app's demo persona when login
 * is off. The persona keeps its own title ("Radiology desk"), which a sign-in
 * does not carry; a signed-in person's role is the server's word, not the app's.
 */
export function useIdentity<R extends string>(persona: Identity<R>): Identity<R> {
  const { principal } = useSession();
  if (!principal) return persona;
  return { name: principal.name, title: persona.title, role: principal.role as R };
}
