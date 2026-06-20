import React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface LoaderProps {
  size?: "sm" | "md" | "lg";
  text?: string;
  className?: string;
  containerClassName?: string;
  fullArea?: boolean; // Centers itself completely in the parent flex/grid container
}

export function Loader({
  size = "md",
  text,
  className,
  containerClassName,
  fullArea = true,
}: LoaderProps) {
  const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-8 w-8",
    lg: "h-12 w-12",
  };

  const loaderElement = (
    <div className={cn("flex flex-col items-center justify-center gap-3", containerClassName)}>
      <Loader2 className={cn("animate-spin text-orange-600 dark:text-orange-500", sizeClasses[size], className)} />
      {text && <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{text}</p>}
    </div>
  );

  if (fullArea) {
    return (
      <div className="flex items-center justify-center w-full h-full min-h-[150px]">
        {loaderElement}
      </div>
    );
  }

  return loaderElement;
}
