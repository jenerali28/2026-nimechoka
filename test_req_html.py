from requests_html import HTMLSession
try:
    session = HTMLSession()
    r = session.get('https://google.com')
    print("Basic GET successful")
    # This might trigger browser download/setup
    # r.html.render() 
    print("Success")
except Exception as e:
    print(f"Failed: {e}")
