# syntax=docker/dockerfile:1.4
# R execution environment with BuildKit optimizations
FROM r-base:4.3.0

# Install system dependencies for R packages (including Cairo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libcairo2-dev \
    libxt-dev \
    libx11-dev \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: Core data manipulation packages (most stable)
RUN R -e "install.packages(c('dplyr', 'tidyr', 'data.table', 'magrittr'), repos='https://cran.rstudio.com/', dependencies=TRUE)"

# Layer 2: Visualization packages (including Cairo for graphics output)
RUN R -e "install.packages(c('ggplot2', 'lattice', 'scales', 'Cairo'), repos='https://cran.rstudio.com/', dependencies=TRUE)"

# Layer 3: Data I/O packages
RUN R -e "install.packages(c('readr', 'readxl', 'writexl', 'jsonlite', 'xml2'), repos='https://cran.rstudio.com/', dependencies=TRUE)"

# Layer 4: Statistics and utilities
RUN R -e "install.packages(c('stats', 'MASS', 'survival', 'lubridate', 'stringr', 'glue'), repos='https://cran.rstudio.com/', dependencies=TRUE)"

# Create non-root user
RUN groupadd -g 1001 codeuser && \
    useradd -r -u 1001 -g codeuser codeuser

# Set working directory and ensure ownership
WORKDIR /mnt/data
RUN chown -R codeuser:codeuser /mnt/data

# Switch to non-root user
USER codeuser

# Set environment variables
ENV R_LIBS_USER=/usr/local/lib/R/site-library

# Default command with sanitized environment
ENTRYPOINT ["/usr/bin/env","-i","PATH=/usr/local/bin:/usr/bin:/bin","HOME=/tmp","TMPDIR=/tmp","R_LIBS_USER=/usr/local/lib/R/site-library"]
CMD ["R", "--version"]
