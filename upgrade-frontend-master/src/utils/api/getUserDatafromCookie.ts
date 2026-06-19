export const getUserDataFromCookie = () => {
  if (typeof document !== "undefined") {
    const cookieString = document.cookie;
    const cookies: { [key: string]: string } = cookieString
      .split("; ")
      .reduce((acc: { [key: string]: string }, cookie) => {
        const [name, value] = cookie.split("=");
        acc[name] = value;
        return acc;
      }, {} as { [key: string]: string });

    if (cookies["userData"]) {
      try {
        return JSON.parse(decodeURIComponent(cookies["userData"]));
      } catch (error) {
        console.error("Error parsing user data from cookie:", error);
        return null;
      }
    }
  }
  return null;
};
