"use client";

import { useEffect, useState, memo } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  RiLockPasswordLine,
  RiRobot2Line,
  RiEyeLine,
  RiEyeOffLine,
} from "react-icons/ri";
import { HiOutlineMail } from "react-icons/hi";
import { cn } from "@/lib/utils";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, LoginFormData } from "@/lib/schemas/auth";
import { useMutation } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { login } from "@/lib/api/auth";
import { showErrorToast, showSuccessToast } from "@/utils/toast";

const AI_MESSAGES = [
  "> QUANTUM_AUTHENTICATION_INIT... 🧠",
  "> NEURAL_HANDSHAKE_ESTABLISHED... ⚡",
  "> BIOMETRIC_SCAN_COMPLETE... 🔍",
  "> SECURING_QUANTUM_CHANNEL... 🌐",
  "> VALIDATING_CREDENTIALS... 🛡️",
  "> ACCESS_PROTOCOLS_READY... ✨",
] as const;

const AiMessage = memo(
  ({ message, className }: { message: string; className?: string }) => (
    <div
      className={cn(
        "transform transition-all duration-500 ease-out",
        "flex items-center gap-2 rounded-lg border border-blue-500/30 bg-black/80 px-4 py-2",
        "shadow-lg shadow-blue-500/20 backdrop-blur-sm",
        "animate-[pulse_3s_ease-in-out_infinite]",
        className
      )}
    >
      <RiRobot2Line className="text-blue-400" />
      <span className="text-sm font-mono text-blue-400 tracking-wide">
        {message}
      </span>
    </div>
  )
);
AiMessage.displayName = "AiMessage";

const LoginPage = () => {
  const router = useRouter();
  // const [aiMessageIndex, setAiMessageIndex] = useState(0);
  const [rememberMe, setRememberMe] = useState(true);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });


  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: async (response) => {
      const token = response.access_token || response.token || response.data?.token || response.data?.access_token;
      showSuccessToast("Login Successful!");
      if (token) {
        localStorage.setItem("access_token", token);
        localStorage.setItem("upgrade-token", token);
      }

      localStorage.removeItem('chat');
      router.push("/chat");
    },
    onError: ()=> {
      showErrorToast("Error Logging in!")
    }
  });

  const onSubmit = (data: LoginFormData) => {
    loginMutation.mutate(data);
  };

  const errorMessage = (loginMutation.error as any)?.response?.data?.message ||
    (loginMutation.error as any)?.response?.data?.error ||
    loginMutation.error?.message;

  return (
    <div className="min-h-screen w-full flex dark:bg-gray-900">
      {/* Left Section */}
      <div className="hidden lg:block lg:w-1/2 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 via-purple-600/20 to-blue-600/20 z-10" />
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/bg.webp')" }}
        />
        <div className="absolute bottom-8 left-8 flex gap-8 text-sm text-white/80 z-20">
          <a
            href="/privacy-policy"
            className="hover:text-white transition-colors"
          >
            Privacy Policy
          </a>
          <a
            href="/terms-and-conditions"
            className="hover:text-white transition-colors"
          >
            Terms of Service
          </a>
        </div>
      </div>

      {/* Right Section */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 lg:p-12 relative">
        <div className="absolute inset-0 bg-grid-white/[0.02] bg-[size:40px_40px] dark:bg-grid-white/[0.05]" />
        <div className="absolute inset-0 bg-gradient-to-br from-blue-100/30 via-transparent to-purple-100/30 dark:from-blue-900/30 dark:to-purple-900/30 backdrop-blur-3xl" />

        <div className="relative w-full max-w-md mx-auto space-y-8">
          {/* <AiMessage
            message={AI_MESSAGES[aiMessageIndex]}
            className="absolute -top-20 left-1/2 -translate-x-1/2 transform"
          /> */}

          <div className="text-center space-y-2">
            <div className="flex justify-center mb-8">
              <Image
                src="/Icon.svg"
                alt="Logo"
                width={40}
                height={40}
                className="animate-pulse"
                priority
              />
            </div>
            <h1 className="text-3xl font-bold dark:text-white">Welcome Back</h1>
            <p className="text-gray-600 dark:text-gray-300">
              Access your AI-powered workspace
            </p>
          </div>

          {errorMessage && (
            <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm">
              {errorMessage}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div className="space-y-4">
              <Input
                {...register("email")}
                type="email"
                placeholder="Email address"
                error={errors.email?.message}
                leftIcon={<HiOutlineMail className="text-gray-400" />}
                className="pl-10 pr-4 py-3 h-12 rounded-lg border bg-white/50 dark:bg-black/50 border-gray-200 dark:border-gray-700 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-600 transition-all"
              />

              <Input
                {...register("password")}
                type="password"
                placeholder="Password"
                error={errors.password?.message}
                leftIcon={<RiLockPasswordLine className="text-gray-400" />}
                className="pl-10 pr-12 py-3 h-12 rounded-lg border bg-white/50 dark:bg-black/50 border-gray-200 dark:border-gray-700 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-600 transition-all"
              />
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-600 dark:text-gray-300">
                  Remember me
                </span>
              </label>

              <button
                type="button"
                onClick={() => router.push("/forgot")}
                className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
              >
                Forgot password?
              </button>
            </div>

            <Button
              type="submit"
              variant="gradient"
              size="lg"
              disabled={loginMutation.isPending}
              className="w-full rounded-lg focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              {loginMutation.isPending ? "Signing in..." : "Sign In"}
            </Button>

            <div className="text-center space-y-2">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Don&apos;t have an account?{" "}
                <button
                  type="button"
                  onClick={() => router.push("/signup")}
                  className="text-blue-600 hover:text-blue-700 dark:text-blue-400"
                >
                  Sign Up
                </button>
              </p>
            </div>
          </form>
        </div>
      </div>
    </div >
  );
};

export default LoginPage;
