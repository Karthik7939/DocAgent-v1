import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";

export const metadata: Metadata = {
  title: "DocuBear",
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
        <main className="w-full px-6 py-6 sm:px-10 lg:px-12">
          <PageTransition>{children}</PageTransition>
        </main>
      </body>
    </html>
  );
}
