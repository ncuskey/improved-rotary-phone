#!/bin/bash
# Check if token broker SSL certificate is ready

echo "🔍 Checking tokens.lothelper.clevergirl.app SSL certificate..."
echo ""

# Test the connection
if curl -I https://tokens.lothelper.clevergirl.app/ 2>&1 | grep -q "HTTP"; then
    echo "✅ SUCCESS! SSL certificate is active and working!"
    echo ""
    echo "Certificate details:"
    curl -v https://tokens.lothelper.clevergirl.app/ 2>&1 | grep -E "subject:|issuer:|expire date:" | sed 's/^/  /'
    echo ""
    echo "🎉 Token broker is now accessible!"
    echo "   Rebuild your iOS app to enable eBay pricing features."
    exit 0
else
    echo "⏳ SSL certificate not yet ready"
    echo ""
    echo "This is normal - Cloudflare certificates can take 5-30 minutes to issue."
    echo "Run this script again in a few minutes to check status."
    echo ""
    echo "Quick check command:"
    echo "  curl -I https://tokens.lothelper.clevergirl.app/"
    exit 1
fi
