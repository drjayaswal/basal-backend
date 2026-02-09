from fastapi_mail import ConnectionConfig
from app.config import settings

get_settings = settings()


def get_category_style(category: str):
    styles = {
        "BUG": {"bg": "#2d1a1a", "text": "#f87171", "label": "Issue Reported"},
        "FEATURE": {"bg": "#1a2d1d", "text": "#4ade80", "label": "New Idea"},
        "UIUX": {"bg": "#1e1b4b", "text": "#818cf8", "label": "Design Feedback"},
        "GENERAL": {"bg": "#171717", "text": "#d4d4d4", "label": "General Note"},
        "OTHER": {"bg": "#262626", "text": "#a3a3a3", "label": "Other"}
    }
    return styles.get(category.upper(), styles["GENERAL"])

def create_html_body(category_key: str, content: str):
    style = get_category_style(category=category_key)
    
    return f"""
    <html>
        <body style="margin: 0; padding: 0; font-family: -apple-system, sans-serif; background-color: #050505; color: #ffffff;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="margin-bottom: 30px; border-left: 4px solid #0284c7; padding-left: 20px; display: flex; align-items: center;">
                    <img src="cid:logo" alt="Basal Logo" style="height: 50px; width: auto; display: block; margin-right: 20px;">
                    <div>
                        <h1 style="text-transform: uppercase; letter-spacing: 2px; font-size: 24px; margin: 0;">
                            Feedback Received<span style="color: #0284c7;">•</span>
                        </h1>
                        <p style="color: #737373; font-size: 10px; text-transform: uppercase; letter-spacing: 3px; margin: 5px 0 0 0;">
                            Bridge the Gap
                        </p>
                    </div>
                </div>
                <p style="font-size: 14px; color: #a3a3a3; line-height: 1.6; margin-bottom: 30px;">
                    Thank you for contributing. We've received your submission and our team has been notified.
                </p>

                <div style="background-color: {style['bg']}; padding: 24px; border-radius: 8px; margin-bottom: 40px;">
                    <div style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {style['text']}; text-transform: uppercase; margin-bottom: 12px;">
                        {style['label']}
                    </div>
                    <div style="font-size: 15px; line-height: 1.6; color: #ffffff; font-style: italic;">
                        "{content}"
                    </div>
                </div>

                <p style="font-size: 13px; color: #525252; line-height: 1.6; margin-bottom: 60px;">
                    Our team reviews every entry. We will reach out via this email address if further details are required.
                </p>

                <div style="border-top: 1px solid #1a1a1a; padding-top: 20px; text-align: center;">
                    <img src="cid:logo" alt="Basal Logo" style="height: 30px; opacity: 0.5;">
                    <p style="font-size: 11px; color: #525252; text-align: center; letter-spacing: 1px;">
                        Sent by Basal™ • Automated System
                    </p>
                </div>
            </div>
        </body>
    </html>
    """

def create_resolve_html_body(category: str, content: str):
    category_key = category.value if hasattr(category, 'value') else str(category)
    
    style = {
        "bg": "#062016", 
        "text": "#10b981", 
        "border": "#059669",
        "label": f"{category_key.upper()} RESOLVED"
    }
    
    return f"""
    <html>
        <body style="margin: 0; padding: 0; font-family: -apple-system, sans-serif; background-color: #050505; color: #ffffff;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="margin-bottom: 30px; border-left: 4px solid #0284c7; padding-left: 20px; display: flex; align-items: center;">
                    <img src="cid:logo" alt="Basal Logo" style="height: 50px; width: auto; display: block; margin-right: 20px;">
                    <div>
                        <h1 style="text-transform: uppercase; letter-spacing: 2px; font-size: 24px; margin: 0;">
                            Feedback Resolved<span style="color: #0284c7;">•</span>
                        </h1>
                        <p style="color: #737373; font-size: 10px; text-transform: uppercase; letter-spacing: 3px; margin: 5px 0 0 0;">
                            Bridge the Gap
                        </p>
                    </div>
                </div>
                <p style="font-size: 14px; color: #a3a3a3; line-height: 1.6; margin-bottom: 30px;">
                    Our Developer team has processed your feedback. The following feedback is <strong>Resolved</strong>
                </p>

                <div style="background-color: {style['bg']}; padding: 24px; border-radius: 8px; margin-bottom: 40px;">
                    <div style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {style['text']}; text-transform: uppercase; margin-bottom: 12px;">
                        {style['label']}
                    </div>
                    <div style="font-size: 15px; line-height: 1.6; color: #ffffff; font-style: italic;">
                        "{content}"
                    </div>
                </div>

                <p style="font-size: 13px; color: #525252; line-height: 1.6; margin-bottom: 60px;">
                    Thank you for helping us refine the Basal™
                </p>

                <div style="border-top: 1px solid #1a1a1a; padding-top: 20px; text-align: center;">
                    <img src="cid:logo" alt="Basal Logo" style="height: 30px; opacity: 0.5;">
                    <p style="font-size: 11px; color: #525252; text-align: center; letter-spacing: 1px;">
                        Sent by Basal™ • Automated System
                    </p>
                </div>
            </div>
        </body>
    </html>
    """


conf = ConnectionConfig(
    MAIL_USERNAME = get_settings.MAIL,
    MAIL_PASSWORD = get_settings.MAIL_PASSWORD,
    MAIL_FROM = get_settings.MAIL,
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)