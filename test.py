import ssl
import certifi

print("SSL Version:", ssl.OPENSSL_VERSION)
print("Default CA File:", ssl.get_default_verify_paths().cafile)
print("Certifi CA File:", certifi.where())


# export SSL_CERT_FILE=/Users/tanhao/Documents/dev/twilio-voice-bot-python/.venv/lib/python3.12/site-packages/certifi/cacert.pem
# export REQUESTS_CA_BUNDLE=/Users/tanhao/Documents/dev/twilio-voice-bot-python/.venv/lib/python3.12/site-packages/certifi/cacert.pem
