FROM wordpress:latest

# Install WP-CLI + tools needed by the import pipeline
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
       curl less mariadb-client unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar \
       -o /usr/local/bin/wp \
    && chmod +x /usr/local/bin/wp
