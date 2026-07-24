import type { ReactNode } from "react";

export const metadata = {
  title: "HumanoidOnline",
  description:
    "Commercial intelligence and transaction infrastructure for the humanoid robotics economy.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
