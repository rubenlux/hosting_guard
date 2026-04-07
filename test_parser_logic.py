
from app.core.log_parser import LogParser

def test_parser():
    raw_logs = """
2024-04-07 10:00:01 [info] Starting PHP-FPM
2024-04-07 10:05:22 [error] PHP Fatal error:  Uncaught Error: Call to undefined function wp_get_current_user() in /var/www/html/wp-content/themes/twentytwentyfour/functions.php:45
Stack trace:
#0 /var/www/html/wp-settings.php(661): include()
#1 /var/www/html/wp-config.php(95): require_once('/var/www/html/w...')
#2 /var/www/html/wp-load.php(50): require_once('/var/www/html/w...')
#3 /var/www/html/wp-blog-header.php(13): require_once('/var/www/html/w...')
#4 /var/www/html/index.php(17): require_once('/var/www/html/w...')
#5 {main}
  thrown in /var/www/html/wp-content/themes/twentytwentyfour/functions.php on line 45
    """
    
    print("--- TESTING LOG PARSER ---")
    errors = LogParser.parse_logs(raw_logs)
    
    if not errors:
        print("FAIL: No errors detected")
        return
        
    for err in errors:
        print(f"Detected: {err['type']} | Severity: {err['severity']}")
        print(f"Message: {err['message']}")
        print(f"File: {err['file']} (Line {err['line']})")
        print("-" * 20)
    
    assert errors[0]['type'] == 'php_error'
    assert errors[0]['line'] == 45
    print("SUCCESS: Log Parser working as expected")

if __name__ == "__main__":
    test_parser()
