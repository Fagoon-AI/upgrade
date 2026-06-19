"use client";

import React, { useState } from "react";
import { Send, Loader2, CheckCircle, Bot, Mail, User } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { showSuccessToast, showErrorToast, showLoadingToast, dismissToast } from "@/utils/toast";

interface FormData {
  name: string;
  email: string;
  use: string;
}

interface ApiSuccessResponse {
  status: "success";
  message: string;
  data: {
    name: string;
    email: string;
    use: string;
    _id: string;
    __v: number;
  };
}

interface ApiErrorResponse {
  status: "fail" | "error";
  message: string;
}

type ApiResponse = ApiSuccessResponse | ApiErrorResponse;

const FuturisticSubscription = () => {
  const [formData, setFormData] = useState<FormData>({
    name: "",
    email: "",
    use: "",
  });
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [touched, setTouched] = useState<Record<keyof FormData, boolean>>({
    name: false,
    email: false,
    use: false,
  });

  const resetForm = () => {
    setFormData({ name: "", email: "", use: "" });
    setTouched({ name: false, email: false, use: false });
    setStatus("idle");
  };

  const validateEmail = (email: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const getValidationError = (field: keyof FormData): string => {
    if (!touched[field]) return "";
    if (!formData[field]) return "This field is required";
    if (field === "email" && !validateEmail(formData.email)) {
      return "Please enter a valid email";
    }
    return "";
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    
    // Validate all fields
    const errors = {
      name: !formData.name,
      email: !formData.email || !validateEmail(formData.email),
      use: !formData.use,
    };

    setTouched({ name: true, email: true, use: true });

    if (Object.values(errors).some(Boolean)) {
      showErrorToast("Please fill in all fields correctly", {
        duration: 3000,
        position: "top-center",
        style: {
          background: "#fee2e2",
          color: "#dc2626",
          border: "1px solid #fecaca",
        },
      });
      return;
    }

    setStatus("loading");
    const loadingToast = showLoadingToast("Submitting your information...", {
      position: "top-center",
    });

    try {
      const response = await fetch("/api/v1/newsletter", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      });

      const data: ApiResponse = await response.json();

      dismissToast(loadingToast);

      if (data.status === "success") {
        setStatus("success");
        showSuccessToast(data.message, {
          duration: 5000,
          position: "top-center",
          style: {
            background: "#dcfce7",
            color: "#16a34a",
            border: "1px solid #bbf7d0",
          },
          icon: "🎉",
        });
        
        // Clear form after successful submission
        setTimeout(() => {
          resetForm();
        }, 2000);
      } else {
        throw new Error(data.message);
      }
    } catch (error) {
      dismissToast(loadingToast);
      setStatus("error");
      showErrorToast(error instanceof Error ? error.message : "Failed to subscribe", {
        duration: 5000,
        position: "top-center",
        style: {
          background: "#fee2e2",
          color: "#dc2626",
          border: "1px solid #fecaca",
        },
      });
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleBlur = (field: keyof FormData) => {
    setTouched(prev => ({
      ...prev,
      [field]: true
    }));
  };

  return (
    <div className="min-h-screen w-full bg-gradient-to-b from-background to-background/95 dark:from-black dark:to-slate-950 flex items-center justify-center p-4 transition-colors duration-300">
      <div className="w-full max-w-3xl relative">
        {/* Animated background effects */}
        <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-blue-500/10 dark:from-purple-500/20 dark:to-blue-500/20 rounded-3xl transition-colors duration-300" />
        <div className="absolute inset-0">
          <div className="absolute top-0 left-1/2 w-96 h-96 -translate-x-1/2 -translate-y-1/2 bg-blue-500/20 dark:bg-blue-500/30 rounded-full blur-3xl animate-pulse" />
          <div className="absolute bottom-0 right-1/2 w-96 h-96 translate-x-1/2 translate-y-1/2 bg-purple-500/20 dark:bg-purple-500/30 rounded-full blur-3xl animate-pulse" />
        </div>

        {/* Main content container */}
        <div className="relative backdrop-blur-xl bg-white/80 dark:bg-black/40 rounded-3xl border border-slate-200 dark:border-white/10 p-8 shadow-2xl transition-all duration-300">
          {/* Header */}
          <div className="mb-8 text-center">
            <div className="w-20 h-20 mx-auto mb-6 relative group">
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500 to-blue-500 rounded-2xl animate-spin-slow blur-xl opacity-50 group-hover:opacity-75 transition-opacity" />
              <div className="relative bg-white/90 dark:bg-black/50 rounded-2xl h-full flex items-center justify-center backdrop-blur-sm border border-slate-200 dark:border-white/10 transition-all duration-300 group-hover:scale-105">
                <Bot className="w-10 h-10 text-slate-900 dark:text-white" />
              </div>
            </div>
            <h2 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-600 to-blue-600 dark:from-purple-400 dark:to-blue-400 mb-2">
              Join the AI Revolution
            </h2>
            <p className="text-slate-600 dark:text-slate-400 text-lg">
              Experience the future of AI with personalized intelligent agents
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Name Input */}
            <div className="relative group">
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500/50 to-blue-500/50 rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="relative flex items-center">
                <User className="absolute left-4 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  onBlur={() => handleBlur("name")}
                  placeholder="Your Name"
                  className="w-full pl-12 pr-4 py-4 bg-white/50 dark:bg-white/5 rounded-lg border border-slate-200 dark:border-white/10 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  disabled={status === "loading"}
                />
              </div>
              {getValidationError("name") && (
                <p className="mt-1 text-sm text-red-500 ml-1">{getValidationError("name")}</p>
              )}
            </div>

            {/* Email Input */}
            <div className="relative group">
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500/50 to-blue-500/50 rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="relative flex items-center">
                <Mail className="absolute left-4 w-5 h-5 text-slate-400" />
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  onBlur={() => handleBlur("email")}
                  placeholder="Your Email"
                  className="w-full pl-12 pr-4 py-4 bg-white/50 dark:bg-white/5 rounded-lg border border-slate-200 dark:border-white/10 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  disabled={status === "loading"}
                />
              </div>
              {getValidationError("email") && (
                <p className="mt-1 text-sm text-red-500 ml-1">{getValidationError("email")}</p>
              )}
            </div>

            {/* Use Case Input */}
            <div className="relative group">
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500/50 to-blue-500/50 rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="relative">
                <textarea
                  name="use"
                  value={formData.use}
                  onChange={handleChange}
                  onBlur={() => handleBlur("use")}
                  placeholder="How do you plan to use our AI?"
                  rows={4}
                  className="w-full px-4 py-4 bg-white/50 dark:bg-white/5 rounded-lg border border-slate-200 dark:border-white/10 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
                  disabled={status === "loading"}
                />
              </div>
              {getValidationError("use") && (
                <p className="mt-1 text-sm text-red-500 ml-1">{getValidationError("use")}</p>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={status === "loading"}
              className="w-full relative group"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500 to-blue-500 rounded-lg blur opacity-75 group-hover:opacity-100 transition-opacity" />
              <div className="relative px-6 py-4 bg-gradient-to-r from-purple-500/90 to-blue-500/90 rounded-lg flex items-center justify-center space-x-2 hover:from-purple-600/90 hover:to-blue-600/90 transition-all">
                <span className="text-white font-semibold">
                  {status === "loading"
                    ? "Processing..."
                    : "Join the Future"}
                </span>
                {status === "loading" ? (
                  <Loader2 className="w-5 h-5 animate-spin text-white" />
                ) : (
                  <Send className="w-5 h-5 text-white group-hover:translate-x-1 transition-transform" />
                )}
              </div>
            </button>
          </form>

          {/* Feature Tags */}
          <div className="mt-8 flex flex-wrap gap-3 justify-center">
            {[
              "Advanced AI Agents",
              "Real-time Processing",
              "Custom Solutions",
              "24/7 Support",
            ].map((feature) => (
              <div
                key={feature}
                className="px-4 py-2 rounded-full bg-slate-100/50 dark:bg-white/5 border border-slate-200 dark:border-white/10 text-sm text-slate-600 dark:text-slate-300 transition-all duration-300 hover:scale-105 hover:bg-slate-100 dark:hover:bg-white/10"
              >
                {feature}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FuturisticSubscription;