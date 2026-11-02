import type { Metadata, Viewport } from "next";
import { Instrument_Serif, Manrope } from "next/font/google";
import "./globals.css";
import "./queryable.css";
import "./tools.css";
import "./settings.css";
import "./lab.css";
import "./admin.css";
import "./workspace.css";

const sans = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
});

const display = Instrument_Serif({
  weight: "400",
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "Queryable Chatbot",
  description: "Ask business questions in plain language; answers come from MongoDB and render as interactive OpenUI views.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#070a16" },
    { media: "(prefers-color-scheme: light)", color: "#f5f6fb" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* @openuidev/react-lang auto-mounts the OpenUI Inspect widget (the
            floating dog button, bottom-right) in development unless this
            global flag is already set. Runs before any app bundle. */}
        <script
          dangerouslySetInnerHTML={{ __html: 'globalThis[Symbol.for("openui.devtools.autoMount")]=true;' }}
        />
      </head>
      <body className={`${sans.variable} ${display.variable}`}>
        {children}
      </body>
    </html>
  );
}
