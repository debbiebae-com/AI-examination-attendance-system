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
    <html lang="en">
      <body>
        <Theme
          className="attendance-theme"
          appearance="light"
          accentColor="teal"
          grayColor="sage"
          radius="medium"
          scaling="100%"
        >
          {children}
        </Theme>
      </body>
    </html>
  );
}
