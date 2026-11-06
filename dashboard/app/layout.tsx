import type { Metadata } from "next";
import { Theme } from "@radix-ui/themes";
import "./globals.css";
export const metadata: Metadata = {
  title: "ExamLens · Live attendance",
  description: "Local face recognition and examination attendance dashboard",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          rel="stylesheet"
          href="https://api.fontshare.com/v2/css?f[]=general-sans@400,500,600,700&display=swap"
        />
      </head>
      <body>
        <Theme
          className="attendance-theme"
          appearance="dark"
          accentColor="orange"
          grayColor="gray"
          radius="medium"
          scaling="100%"
        >
          {children}
        </Theme>
      </body>
    </html>
  );
}
