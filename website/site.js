(() => {
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const targets = document.querySelectorAll(".statement, .process article, .case-study, .feature-section, .features article, .interface, .closing");
    targets.forEach((element) => element.classList.add("reveal"));
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    targets.forEach((element) => observer.observe(element));
  }

  const trigger = document.querySelector("#load-paypal-donate");
  const container = document.querySelector("#donate-button-container");
  if (!trigger || !container) return;
  const isEnglish = document.documentElement.lang === "en";

  trigger.addEventListener("click", () => {
    trigger.disabled = true;
    trigger.textContent = isEnglish ? "Loading PayPal donate button …" : "PayPal-Button wird geladen …";
    const script = document.createElement("script");
    script.src = "https://www.paypalobjects.com/donate/sdk/donate-sdk.js";
    script.charset = "UTF-8";
    script.onload = () => {
      const mount = document.createElement("div");
      mount.id = "donate-button";
      container.replaceChildren(mount);
      window.PayPal.Donation.Button({
        env: "production",
        hosted_button_id: "SY8DQRZTPETRA",
        image: {
          src: "https://www.paypalobjects.com/de_DE/DE/i/btn/btn_donateCC_LG.gif",
          alt: "Spenden mit dem PayPal-Button",
          title: "PayPal - The safer, easier way to pay online!"
        }
      }).render("#donate-button");
    };
    script.onerror = () => {
      trigger.disabled = false;
      trigger.textContent = isEnglish ? "PayPal donate button could not be loaded" : "PayPal-Button konnte nicht geladen werden";
      trigger.classList.add("donate-status");
    };
    document.head.append(script);
  });
})();
