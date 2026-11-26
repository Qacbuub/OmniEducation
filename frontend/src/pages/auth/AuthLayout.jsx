import logo from "../../assets/omniteckno-logo.png";

export default function AuthLayout({ children }) {
  return (
    <div className="auth">
      <section className="auth__brand" aria-label="About OmniEducation">
        <img className="auth__logo" src={logo} alt="OmniTeckno" />
        <div style={{ position: "relative", zIndex: 1 }}>
          <div className="eyebrow" style={{ color: "var(--brand)" }}>OmniEducation</div>
          <h1 className="auth__headline">One secure platform for <span>schools</span> and <span>universities</span>.</h1>
          <p className="auth__lead">
            Admissions, academics, attendance, results, transcripts and fees, with every institution's data kept isolated and protected.
          </p>
          <div className="auth__modes">
            <div className="auth__mode"><strong>School (K-12)</strong><span>Classes · terms · report cards · promotion</span></div>
            <div className="auth__mode"><strong>University</strong><span>Courses · credits · GPA · transcripts</span></div>
          </div>
        </div>
        <div className="auth__foot">© {new Date().getFullYear()} OmniTeckno, an OmniOS company · A Safer Digital Tomorrow</div>
      </section>
      <section className="auth__panel">
        <div style={{ width: "100%", maxWidth: 400 }}>
          <div className="auth__mobile-logo"><img src={logo} alt="OmniTeckno" /></div>
          {children}
        </div>
      </section>
    </div>
  );
}
