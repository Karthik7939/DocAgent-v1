import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "DocAgent",
  description: "Automated code documentation, reviewed by you.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main className="mx-auto w-full max-w-7xl px-5 py-6 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
