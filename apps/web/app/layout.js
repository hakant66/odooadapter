export const metadata = {
  title: "Odoo Adapter Control Plane",
  description: "Monitor and control bi-directional syncs"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "'IBM Plex Sans', sans-serif", background: "#f4f7f8", color: "#0d2026" }}>
        {children}
      </body>
    </html>
  );
}
