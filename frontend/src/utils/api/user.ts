interface User {
  name: string;
  email: string;
  token?: string;
}

export const getUserName = (): string => {
  if (typeof window !== "undefined") {
    const user = localStorage.getItem("user");
    if (user) {
      try {
        const parsedUser = JSON.parse(user);
        return parsedUser.name;
      } catch (error) {
        console.error("Error parsing user data:", error);
      }
    }
  }
  return "Guest User";
};

export const getGreeting = (): string => {
  const currentHour = new Date().getHours();

  if (currentHour < 12) {
    return "Good Morning";
  } else if (currentHour < 18) {
    return "Good Afternoon";
  } else {
    return "Good Evening";
  }
};

export const getUser = (): User | null => {
  if (typeof window === "undefined") return null;

  try {
    const userStr = localStorage.getItem("user");
    if (userStr) {
      return JSON.parse(userStr);
    }
  } catch (error) {
    console.error("Error getting user:", error);
  }

  return null;
};

export const isLoggedIn = (): boolean => {
  return !!getUser();
};

export const logout = async (): Promise<void> => {
  try {
    // Clear session storage
    sessionStorage.removeItem("chatMessages");

    // Clear local storage
    localStorage.removeItem("user");
    localStorage.removeItem("name");

    // Optional: Call logout API
    await fetch("/api/v1/users/logout");
  } catch (error) {
    console.error("Logout error:", error);
  }
};
