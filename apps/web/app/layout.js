export const metadata = {
  title: "Odoo Adapter Workflow Console",
  description: "Operate tenant setup, Odoo connection, inbound email sync, and job controls"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "'IBM Plex Sans', 'Avenir Next', 'Segoe UI', sans-serif",
          color: "#102926",
          background:
            "radial-gradient(circle at 15% 10%, #d9ebe7 0%, #eaf3f2 35%, #f4f8f7 70%), linear-gradient(180deg, #f4f8f7, #edf4f2)",
          minHeight: "100vh"
        }}
      >
        {children}
      </body>
    </html>
  );
}
