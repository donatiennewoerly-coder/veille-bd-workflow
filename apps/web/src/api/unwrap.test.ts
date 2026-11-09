import { describe, expect, test } from "bun:test";

import { dataOr404, unwrap } from "./unwrap";

describe("unwrap", () => {
  test("normalizes FastAPI detail responses into Error instances", async () => {
    try {
      // oxlint-disable-next-line eslint/prefer-promise-reject-errors, typescript/prefer-promise-reject-errors -- the generated client rejects with the raw response body, which is what unwrap normalizes
      await unwrap(Promise.reject({ detail: "Workflow failed" }));
      throw new Error("Expected unwrap to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      // SAFETY: the expect above fails the test unless `error` is an Error instance.
      // oxlint-disable-next-line typescript/no-unsafe-type-assertion -- see SAFETY
      expect((error as Error).message).toBe("Workflow failed");
    }
  });
});

/**
 * A refusal body: FastAPI's (a message, a refused form's fields, or a structured refusal), or what
 * a gateway or proxy answers instead (an HTML page, plain text, JSON without a readable `detail`).
 */
type Refusal =
  | {
      detail:
        | string
        | readonly { loc: readonly (string | number)[]; msg: string }[]
        | { message: string; problems: readonly string[] };
    }
  | { detail: { code: string } | null }
  | string
  | { error: string };

/** What APISIX answers while the API is down: an HTML page, padded for old browsers. */
const GATEWAY_PAGE =
  "<html>\r\n<head><title>503 Service Temporarily Unavailable</title></head>\r\n<body>\r\n<center><h1>503 Service Temporarily Unavailable</h1></center>\r\n<hr><center>openresty</center>\r\n</body>\r\n</html>\r\n<!-- a padding to disable MSIE and Chrome friendly error page -->\r\n";

/** The message `unwrap` gives a request the server refused with `body`. */
const message = async (body: Refusal): Promise<string> => {
  try {
    // oxlint-disable-next-line typescript/prefer-promise-reject-errors -- the generated client rejects with the raw response body, which is what unwrap normalizes
    await unwrap(Promise.reject(body));
  } catch (error) {
    if (error instanceof Error) {
      return error.message;
    }
  }

  throw new Error("Expected unwrap to reject");
};

describe("refusals in words", () => {
  test("a refused form names each field", async () => {
    const refused = {
      detail: [
        {
          loc: ["body", "phone"],
          msg: "Value error, The phone number must be in E.164 form",
        },
        {
          loc: ["body", "signals", 0, "weight"],
          msg: "Input should be less than 1",
        },
      ],
    };

    expect(await message(refused)).toBe(
      "phone: The phone number must be in E.164 form · signals.0.weight: Input should be less than 1"
    );
  });

  test("a structured refusal reads its message", async () => {
    expect(
      await message({
        detail: { message: "The import was refused.", problems: [] },
      })
    ).toBe("The import was refused.");
  });

  test("only a readable detail is a message: a gateway's page or any other body is not", async () => {
    expect(await message(GATEWAY_PAGE)).toBe("The request failed.");
    expect(await message("Bad Gateway")).toBe("The request failed.");
    expect(await message({ error: "upstream timeout" })).toBe(
      "The request failed."
    );
    expect(await message({ detail: { code: "E42" } })).toBe(
      "The request failed."
    );
    expect(await message({ detail: null })).toBe("The request failed.");
  });

  test("a failed read through dataOr404 reads a gateway's page as a plain sentence", () => {
    expect(() =>
      dataOr404({ error: GATEWAY_PAGE }, () => new RangeError("gone"))
    ).toThrow("The request failed.");
  });

  test("a read answers a 404 as the caller's own error", () => {
    const missing = new Response(null, { status: 404 });
    expect(() =>
      dataOr404(
        { error: { detail: "Unknown call" }, response: missing },
        () => new RangeError("gone")
      )
    ).toThrow(RangeError);
    expect(
      dataOr404(
        { data: 1, response: new Response(null, { status: 200 }) },
        () => new RangeError("gone")
      )
    ).toBe(1);
    expect(() =>
      dataOr404({ error: { detail: "Down" } }, () => new RangeError("gone"))
    ).toThrow("Down");
  });
});
