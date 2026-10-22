import "./style.css";
export const metadata = {
  title: "InferenceFlow",
  description: "Asynchronous inference execution and prepaid usage",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
