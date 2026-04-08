import brandLogo from "../assets/brand-mark.svg";
import "./LoadingLogo.css";

export default function LoadingLogo({
  className = "",
  label = "Loading",
  size = 128,
}) {
  const classes = ["loading-logo"];
  if (className) classes.push(className);

  return (
    <div className={classes.join(" ")} role="status" aria-live="polite" aria-label={label}>
      <img
        className="loading-logo-image"
        src={brandLogo}
        alt=""
        aria-hidden="true"
        style={{ width: size, height: "auto" }}
      />
    </div>
  );
}


