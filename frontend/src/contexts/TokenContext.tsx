'use client';

import React, { createContext, useContext, useState } from 'react';

interface TokenType {
  token: number;
  setToken: React.Dispatch<React.SetStateAction<number>>;
}

const TokenContext = createContext<TokenType | undefined>(undefined);

export const useTokenContext = () => {
  const context = useContext(TokenContext);
  if (!context) {
    throw new Error('useTokenContext must be used within a TokenProvider');
  }
  return context;
};

interface TokenProviderProps {
  children: React.ReactNode;
}

export const TokenProvider: React.FC<TokenProviderProps> = ({ children }) => {
  const [token, setToken] = useState<number>(0);

  return (
    <TokenContext.Provider value={{ token, setToken }}>
      {children}
    </TokenContext.Provider>
  );
};
