export const domainBase = () => {
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    if (hostname == "upgrade.fagoondigital.com") {
      return "fagoondigital.com";
    } else if (hostname == "fagoon.tech") {
      return "fagoon.ai";
    }
  }
      return "fagoon.ai";
  // return "fagoondigital.com";
};

export const baseAPIdomain = process.env.AI_API_URL;

// let baseAPIdomain = "https://fagoon.tech/upgrade";

// if(ENV === "development") {
//   baseAPIdomain = "https://saugatregmi.ekrasunya.com";
// }

// export { baseAPIdomain };

// // // export const baseAPIdomain = "https://saugatregmi.ekrasunya.com";
// // export const baseAPIdomain = `https://fagoon.tech/upgrade`;
