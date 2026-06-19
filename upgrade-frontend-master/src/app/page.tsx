"use client";

import { useRouter } from "next/navigation";
import React, { useEffect } from "react";
import dynamic from "next/dynamic";

const Lottie = dynamic(() => import("lottie-react"), { ssr: false });
import animationData from "../../public/upgrade.json";

const Homepage = () => {
  const router = useRouter();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const timer = setTimeout(() => {
        router.replace("/chat");
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [router]);

  return (
    <div className="h-screen w-screen fixed flex items-center justify-center bg-[#0a0a0a] text-white">
      <div className="bg-[#A020F0]/80 absolute top-[-164px] left-[136px] h-[300px] w-[50px] rounded-full blur-[7rem] sm:w-[300px] transition-all duration-500"></div>
      <Lottie
        animationData={animationData}
        loop={true}
        style={{ height: "100px", width: "100px" }}
      />
      <div className="text-[50px] font-bold tracking-widest ml-4">UPGRADE</div>
    </div>
  );
};

export default Homepage;
