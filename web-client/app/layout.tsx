import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LoL Companion",
  description: "Real-time League of Legends chatbot companion",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
