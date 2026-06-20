"use client";

import { toast as toastify, ToastContainer as BaseToastContainer, ToastOptions, ToastContainerProps } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import { useTheme } from "next-themes";

export const showSuccessToast = (message: string, options?: ToastOptions) => {
    return toastify.success(message, {
        ...options
    });
};

export const showErrorToast = (message: string, options?: ToastOptions) => {
    return toastify.error(message, {
        ...options
    });
};

export const showAlertToast = (message: string, options?: ToastOptions) => {
    return toastify.warning(message, {
        ...options
    });
};

export const showInfoToast = (message: string, options?: ToastOptions) => {
    return toastify.info(message, {
        ...options
    });
};

export const showLoadingToast = (message: string, options?: ToastOptions) => {
    return toastify.loading(message, {
        ...options
    });
};

export const dismissToast = (id?: string | number) => {
    return toastify.dismiss(id);
};

export const ToastContainer = (props: ToastContainerProps) => {
    const { theme } = useTheme();
    return (
        <BaseToastContainer 
            theme={theme === "dark" ? "dark" : "light"} 
            {...props} 
        />
    );
};
