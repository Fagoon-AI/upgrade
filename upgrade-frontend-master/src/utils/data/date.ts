export function HumanizeTimestamp(isoTimestamp?: string): string {
  if (!isoTimestamp) return "";

  const timestamp = new Date(isoTimestamp);
  const now = new Date();

  const seconds = Math.floor((now.getTime() - timestamp.getTime()) / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 7) {
    return formatDate(timestamp.toLocaleDateString());
  } else if (days > 0) {
    return `${days} days ago`;
  } else {
    return `Today`;
  }
}

const formatDate = (inputDate: string): string => {
  const [day, month, year] = inputDate.split("/").map(Number);
  const date = new Date(year, month - 1, day);

  const daySuffix = (d: number): string => {
    if (d > 3 && d < 21) return "th";
    switch (d % 10) {
      case 1:
        return "st";
      case 2:
        return "nd";
      case 3:
        return "rd";
      default:
        return "th";
    }
  };

  const months: string[] = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];

  const formattedDate = `${date.getDate()}${daySuffix(date.getDate())} ${months[date.getMonth()]
    } ${date.getFullYear()}`;
  return formattedDate;
};