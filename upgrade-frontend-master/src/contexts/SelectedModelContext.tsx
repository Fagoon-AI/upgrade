"use client";

import React, { createContext, useContext, useState } from "react";

interface SelectedModelContextType {
  selectedModel: string;
  setSelectedModel: React.Dispatch<React.SetStateAction<string>>;
}

const SelectedModelContext = createContext<
  SelectedModelContextType | undefined
>(undefined);

export const useSelectedModelContext = () => {
  const context = useContext(SelectedModelContext);
  if (!context) {
    throw new Error(
      "useSelectedModelContext must be used within a SelectedModelProvider"
    );
  }
  return context;
};

interface SelectedModelProviderProps {
  children: React.ReactNode;
}

export const SelectedModelProvider: React.FC<SelectedModelProviderProps> = ({
  children,
}) => {
  const defaultSelectedModel = "gemini-2.5-flash";

  const [selectedModel, setSelectedModel] =
    useState<string>(defaultSelectedModel);

  return (
    <SelectedModelContext.Provider value={{ selectedModel, setSelectedModel }}>
      {children}
    </SelectedModelContext.Provider>
  );
};
