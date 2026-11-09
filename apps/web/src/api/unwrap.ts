import { z } from "zod";

/** One field FastAPI refused (422), named by its path under the request: "phone: …". */
const fieldProblem = z
  .object({ loc: z.array(z.union([z.string(), z.number()])), msg: z.string() })
  .transform(({ loc, msg }) => {
    const field = loc
      .filter((part) => !["body", "query", "path"].includes(String(part)))
      .join(".");

    const message = msg.replace(/^Value error, /u, "");

    return field ? `${field}: ${message}` : message;
  });

// With `throwOnError: true` the generated client rejects with the raw parsed response body (for
// example FastAPI's `{ detail: ... }`), which is not an `Error`, so UI that reads `err.message`
// renders nothing. The rejection is parsed here, at the client boundary, into a message: the
// server's own, a refused form's field problems ("phone: …" · "due_on: …"), or a structured
// refusal's `message`. Only those `detail` shapes are a message: any other body (a gateway's HTML
// error page while the API is down, a proxy's plain text, JSON without a readable `detail`) reads
// as a plain sentence instead.
const rejection = z.union([
  z.object({ detail: z.string() }).transform(({ detail }) => detail),
  z
    .object({ detail: z.array(fieldProblem).min(1) })
    .transform(({ detail }) => detail.join(" · ")),
  z
    .object({ detail: z.object({ message: z.string() }) })
    .transform(({ detail }) => detail.message),
  z.unknown().transform(() => "The request failed."),
]);

/** Unwraps a hey-api SDK result: the typed data, or a real `Error` carrying the server's message. */
export const unwrap = async <T>(promise: Promise<{ data: T }>): Promise<T> => {
  try {
    const result = await promise;

    return result.data;
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }

    throw new Error(rejection.parse(error), { cause: error });
  }
};

/**
 * A hey-api result read without `throwOnError`: its data, `notFound()` for a 404 (a record that does
 * not exist, which no retry fixes), or an `Error` carrying the server's message.
 */
export const dataOr404 = <T>(
  result: { data?: T; error?: unknown; response?: Response },
  notFound: () => Error
): T => {
  if (result.response?.status === 404) {
    throw notFound();
  }

  if (result.error !== undefined || result.data === undefined) {
    throw new Error(rejection.parse(result.error), { cause: result.error });
  }

  return result.data;
};
