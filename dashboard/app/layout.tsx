import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "ExamLens · Live attendance", description: "Local face recognition and examination attendance dashboard" };
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
