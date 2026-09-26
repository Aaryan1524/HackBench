import type { Metadata } from "next";
import localFont from "next/font/local";
import { Lora } from "next/font/google";
import "./globals.css";
import AnalyticsInit from "@/components/AnalyticsInit";
import VercelAnalytics from "@/components/VercelAnalytics";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});

const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "HackBench — Feedback on your hackathon idea or project",
  description:
    "Review an idea before you build, or a project once it works. See what is strong, what is missing, and what to do next.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${lora.variable} ${geistSans.variable} ${geistMono.variable} antialiased bg-canvas text-ink font-sans min-h-screen selection:bg-[#EBE8DF] selection:text-ink`}
      >
        <AnalyticsInit />
        <VercelAnalytics />
        {children}
      </body>
    </html>
  );
}
