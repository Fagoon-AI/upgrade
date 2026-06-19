import { useRouter } from "next/navigation";
import { useUserStore } from "@/lib/store/user";

export const useUser = () => {
  const { user, token, logout } = useUserStore();
  const router = useRouter();

  const userName = user?.name || user?.nickname || "User";
  const isAuthenticated = !!(user && token);

  const handleLogout = async () => {
    logout();
    router.push("/login");
  };

  return {
    userName,
    isAuthenticated,
    logout: handleLogout,
  };
};
