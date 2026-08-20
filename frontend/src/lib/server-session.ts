export const SESSION_COOKIE_NAME =
  process.env.NODE_ENV === "production" ? "__Host-tm_session" : "tm_session";

export const SESSION_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 8;
