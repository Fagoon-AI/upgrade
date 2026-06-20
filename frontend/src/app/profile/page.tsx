"use client";

import { useState, useEffect } from "react";
import { showSuccessToast, showErrorToast } from "@/utils/toast";
import { useTheme } from "next-themes";
import { Dialog, DialogTrigger, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import ApiKeyDialog from "./api-key-dialog";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { userPreferencesSchema, UserPreferencesFormData } from "@/lib/schemas/user";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import * as userApi from "@/lib/api/user";
import * as authApi from "@/lib/api/auth";

export default function Profile() {
  const { setTheme } = useTheme();
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const router = useRouter();
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UserPreferencesFormData>({
    resolver: zodResolver(userPreferencesSchema),
  });

  const { data: profileData, isLoading: loading, error: fetchError } = useQuery({
    queryKey: ['userPreferences'],
    queryFn: async () => {
      try {
        const response = await userApi.getUserPreferences();
        if (response.success && response.data) {
          return response.data;
        }
        throw new Error("Invalid response format");
      } catch (err: any) {
        if (err.response?.status === 404) {
          // If user preferences don't exist, create them
          const creationResponse = await userApi.updateUserPreferences({});
          return creationResponse.data;
        }
        throw err;
      }
    },
  });

  useEffect(() => {
    if (profileData) {
      reset({
        nickname: profileData.nickname || "",
        location: profileData.location || "",
        role: profileData.role || "",
        systemPrompt: profileData.systemPrompt || "",
        theme: profileData.theme || "light",
        bio: profileData.bio || "",
        responseTone: profileData.responseTone || "professional",
      });
    }
  }, [profileData, reset]);

  const updateProfileMutation = useMutation({
    mutationFn: userApi.updateUserPreferences,
    onSuccess: (responseData) => {
      if (responseData.success && responseData.data) {
        queryClient.setQueryData(['userPreferences'], responseData.data);
        setTheme(responseData.data.theme);
        setIsEditing(false);
        showSuccessToast("Profile updated successfully", {
          duration: 3000,
          icon: '👍',
        });
      }
    },
    onError: (err: any) => {
      console.error("Update error:", err);
      if (err.response?.data?.errors && err.response.data.errors.length > 0) {
        err.response.data.errors.forEach((error: string) => showErrorToast(error));
      } else {
        showErrorToast(err.response?.data?.message || err.message || "Failed to update profile");
      }
    }
  });

  const onSubmit = (data: UserPreferencesFormData) => {
    updateProfileMutation.mutate(data);
  };

  const cancelEditing = () => {
    if (profileData) {
      reset({
        nickname: profileData.nickname || "",
        location: profileData.location || "",
        role: profileData.role || "",
        systemPrompt: profileData.systemPrompt || "",
        theme: profileData.theme || "light",
        bio: profileData.bio || "",
        responseTone: profileData.responseTone || "professional",
      });
    }
    setIsEditing(false);
  };

  const getInitials = (name?: string): string => {
    if (!name) return "U";
    const words = name.split(/\s+/).filter((word) => word.length > 0);
    if (words.length >= 2) {
      return (words[0][0] + words[1][0]).toUpperCase();
    }
    return name.charAt(0).toUpperCase();
  };

  const onValidateGoogleWorkspace = async () => {
    try {
      const response = await authApi.googleLogin()
      const url = response.auth_url
      router.replace(url)
    } catch (e) {
      console.log(e)
      showSuccessToast('Unable to verify google')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen w-full">
        <div className="flex flex-col items-center space-y-2">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500"></div>
          <p className="text-gray-600 dark:text-gray-300">Loading profile...</p>
        </div>
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="flex items-center justify-center min-h-screen w-full text-red-500">
        Failed to load profile. Please try refreshing.
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full">
      <main className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <div className=" rounded-lg shadow-md overflow-hidden border border-gray-200 dark:border-gray-700 transition-all">
            <div className="p-4 md:p-6">
              {!isEditing ? (
                <>
                  <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
                    <div className="bg-gradient-to-br from-blue-500 to-purple-600 w-16 h-16 md:w-20 md:h-20 rounded-full flex items-center justify-center text-white text-xl md:text-2xl font-bold shadow-md">
                      {getInitials(profileData?.nickname)}
                    </div>

                    <div className="flex-1">
                      <h1 className="text-xl md:text-2xl font-bold text-gray-800 dark:text-white">
                        {profileData?.nickname || "User"}
                      </h1>
                      <p className="text-gray-500 dark:text-gray-400">
                        {profileData?.role || "No role specified"}
                      </p>
                    </div>

                    <button
                      onClick={() => setIsEditing(true)}
                      className="sm:ml-auto px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition duration-200 text-sm flex items-center shadow-sm"
                      aria-label="Edit Profile"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-4 w-4 mr-1"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                      </svg>
                      Edit Profile
                    </button>
                  </div>

                  <div className="mt-6 space-y-6">
                    {profileData?.location && (
                      <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-300">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-5 w-5 text-gray-500 dark:text-gray-400"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                        </svg>
                        <span>{profileData.location}</span>
                      </div>
                    )}

                    {profileData?.bio && (
                      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold mb-3 text-gray-800 dark:text-white">
                          About
                        </h2>
                        <p className="text-gray-600 dark:text-gray-300 whitespace-pre-line">
                          {profileData.bio}
                        </p>
                      </div>
                    )}

                    {profileData?.systemPrompt && (
                      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold mb-3 text-gray-800 dark:text-white">
                          System Prompt
                        </h2>
                        <div className="bg-gray-50 dark:bg-gray-700 p-3 rounded-md text-gray-600 dark:text-gray-300 text-sm font-mono whitespace-pre-line overflow-auto max-h-40">
                          {profileData.systemPrompt}
                        </div>
                      </div>
                    )}

                    <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                      <h2 className="text-lg font-semibold mb-3 text-gray-800 dark:text-white">
                        Settings
                      </h2>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="flex items-center justify-between">
                          <span className="text-gray-600 dark:text-gray-300">
                            Theme
                          </span>
                          <span className="px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full text-sm text-gray-700 dark:text-gray-300">
                            {profileData?.theme || "light"}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-gray-600 dark:text-gray-300">
                            Response Tone
                          </span>
                          <span className="px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full text-sm text-gray-700 dark:text-gray-300">
                            {profileData?.responseTone || "professional"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                  <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 pb-4">
                    <h2 className="text-xl font-bold text-gray-800 dark:text-white">
                      Edit Profile
                    </h2>
                    <button
                      type="button"
                      onClick={cancelEditing}
                      className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                      aria-label="Cancel editing"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-5 w-5"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
                    <div className="space-y-1">
                      <label
                        htmlFor="nickname"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Nickname <span className="text-xs text-gray-500">(max 30 chars)</span>
                      </label>
                      <Input
                        {...register("nickname")}
                        id="nickname"
                        error={errors.nickname?.message}
                        className="bg-white/40 dark:bg-black/40"
                        placeholder="Your nickname"
                      />
                    </div>

                    <div className="space-y-1">
                      <label
                        htmlFor="role"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Role <span className="text-xs text-gray-500">(max 50 chars)</span>
                      </label>
                      <Input
                        {...register("role")}
                        id="role"
                        error={errors.role?.message}
                        className="bg-white/40 dark:bg-black/40"
                        placeholder="Your role"
                      />
                    </div>

                    <div className="space-y-1">
                      <label
                        htmlFor="location"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Location <span className="text-xs text-gray-500">(max 100 chars)</span>
                      </label>
                      <Input
                        {...register("location")}
                        id="location"
                        error={errors.location?.message}
                        className="bg-white/40 dark:bg-black/40"
                        placeholder="Your location"
                      />
                    </div>

                    <div className="space-y-1">
                      <label
                        htmlFor="theme"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Theme
                      </label>
                      <div className="relative">
                        <select
                          {...register("theme")}
                          id="theme"
                          className="w-full px-3 h-9 border border-input rounded-md focus:outline-none focus:ring-1 focus:ring-ring bg-white/40 dark:bg-black/40 text-sm shadow-sm transition-colors text-gray-800 dark:text-gray-200 appearance-none"
                          aria-label="Select theme"
                        >
                          <option value="light">Light</option>
                          <option value="dark">Dark</option>
                        </select>
                        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-chevron-down"><path d="m6 9 6 6 6-6"/></svg>
                        </div>
                      </div>
                      <div className="min-h-[1.25rem]" /> {/* Spacer to align with inputs */}
                    </div>

                    <div className="space-y-1">
                      <label
                        htmlFor="responseTone"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Response Tone
                      </label>
                      <div className="relative">
                        <select
                          {...register("responseTone")}
                          id="responseTone"
                          className="w-full px-3 h-9 border border-input rounded-md focus:outline-none focus:ring-1 focus:ring-ring bg-white/40 dark:bg-black/40 text-sm shadow-sm transition-colors text-gray-800 dark:text-gray-200 appearance-none"
                          aria-label="Select response tone"
                        >
                          <option value="professional">Professional</option>
                          <option value="friendly">Friendly</option>
                          <option value="casual">Casual</option>
                          <option value="formal">Formal</option>
                        </select>
                        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-chevron-down"><path d="m6 9 6 6 6-6"/></svg>
                        </div>
                      </div>
                      <div className="min-h-[1.25rem]" /> {/* Spacer to align with inputs */}
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label
                      htmlFor="bio"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                    >
                      Bio <span className="text-xs text-gray-500">(max 500 chars)</span>
                    </label>
                    <Textarea
                      {...register("bio")}
                      id="bio"
                      rows={4}
                      error={errors.bio?.message}
                      className="bg-white/40 dark:bg-black/40"
                      placeholder="Tell us about yourself"
                    />
                  </div>

                  <div className="space-y-1">
                    <label
                      htmlFor="systemPrompt"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                    >
                      System Prompt <span className="text-xs text-gray-500">(max 1000 chars)</span>
                    </label>
                    <Textarea
                      {...register("systemPrompt")}
                      id="systemPrompt"
                      rows={4}
                      error={errors.systemPrompt?.message}
                      className="bg-white/40 dark:bg-black/40 font-mono"
                      placeholder="Enter your system prompt"
                    />
                  </div>

                  <div className="flex mt-6 gap-3 justify-end">
                    <button
                      type="button"
                      onClick={cancelEditing}
                      className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300"
                      disabled={updateProfileMutation.isPending}
                      aria-label="Cancel"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center"
                      disabled={updateProfileMutation.isPending}
                      aria-label="Save changes"
                    >
                      {updateProfileMutation.isPending ? (
                        <>
                          <svg
                            className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                            xmlns="http://www.w3.org/2000/svg"
                            fill="none"
                            viewBox="0 0 24 24"
                          >
                            <circle
                              className="opacity-25"
                              cx="12"
                              cy="12"
                              r="10"
                              stroke="currentColor"
                              strokeWidth="4"
                            ></circle>
                            <path
                              className="opacity-75"
                              fill="currentColor"
                              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                            ></path>
                          </svg>
                          Saving...
                        </>
                      ) : (
                        <>
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-4 w-4 mr-1"
                            viewBox="0 0 20 20"
                            fill="currentColor"
                          >
                            <path
                              fillRule="evenodd"
                              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                              clipRule="evenodd"
                            />
                          </svg>
                          Save Changes
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
          <div className="flex items-end mt-2 justify-end gap-2">
            <Button onClick={onValidateGoogleWorkspace}>Validate Google</Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant={'outline'}>Get API Key</Button>
              </DialogTrigger>
              <DialogTitle className="sr-only">Generate API Key</DialogTitle>
              <DialogContent>
                <ApiKeyDialog />
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </main>
    </div>
  );
}
