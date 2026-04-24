import type { Metadata } from "next";
import { Share_Tech_Mono, Rajdhani } from "next/font/google";
import "./globals.css";

const mono = Share_Tech_Mono({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-mono",
});

const display = Rajdhani({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "JobRight Feed",
  description: "Aryan Chaudhary — Live job recommendations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${mono.variable} ${display.variable}`}>
      <body>{children}</body>
    </html>
  );
}
