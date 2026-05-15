# Force project logs and R warnings to English when the system supports it.
.scflow_set_english_locale <- function() {
  Sys.setenv(LANGUAGE = "en", LANG = "en_US.UTF-8")
  for (loc in c("en_US.UTF-8", "C.UTF-8", "C")) {
    ok <- tryCatch({
      res <- suppressWarnings(Sys.setlocale("LC_MESSAGES", loc))
      !is.na(res) && nzchar(res)
    }, error = function(e) FALSE)
    if (isTRUE(ok)) break
  }
}
.scflow_set_english_locale()

library(ggplot2)
library(grDevices)

pick_cjk_font_family <- function() {
  if (!identical(Sys.info()[["sysname"]], "Darwin")) {
    return("")
  }
  for (family in c("PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS")) {
    probe <- tryCatch({
      grDevices::quartzFonts(scflow_cjk = grDevices::quartzFont(rep(family, 4)))
      TRUE
    }, error = function(e) FALSE)
    if (isTRUE(probe)) {
      return("scflow_cjk")
    }
  }
  ""
}

sc_base_family <- pick_cjk_font_family()

# Unified plot styling and multi-format export helpers.
# All plots are exported as PNG + PDF + SVG by default so the export page
# can directly collect full-resolution raster and vector outputs.

colors_soft <- c(
  "#3B6FB6", "#D95F02", "#1B9E77", "#7570B3", "#E7298A",
  "#66A61E", "#E6AB02", "#A6761D", "#A6CEE3", "#B2DF8A",
  "#FB9A99", "#FDBF6F", "#CAB2D6", "#8DD3C7", "#BEBADA",
  "#80B1D3", "#FB8072", "#B3DE69", "#FCCDE5", "#BC80BD",
  "#CCEBC5", "#FFED6F", "#4E79A7", "#F28E2B", "#59A14F",
  "#9C755F", "#BAB0AC", "#86BCB6", "#D37295", "#A0CBE8"
)

colors_dark <- c(
  "#C44E52", "#4C72B0", "#55A868", "#8172B3", "#CCB974",
  "#64B5CD", "#8C8C8C", "#937860", "#DA8BC3", "#8C564B",
  "#4DB6AC", "#90A4AE", "#F4A261", "#2A9D8F", "#E76F51",
  "#6D597A", "#B56576", "#355070", "#43AA8B", "#F9C74F",
  "#577590", "#F9844A", "#6A994E", "#7B6D8D", "#A8DADC",
  "#457B9D", "#E63946", "#B8DE6F", "#D4A373", "#84A59D"
)

colors_pub <- c(
  "#0077BB", "#33BBEE", "#009988", "#EE7733", "#CC3311",
  "#EE3377", "#BBBBBB", "#004488", "#228833", "#AA3377",
  "#66CCEE", "#4477AA", "#44AA99", "#117733", "#999933",
  "#DDCC77", "#CC6677", "#882255", "#332288", "#88CCEE",
  "#117733", "#DDCC77", "#CC6677", "#AA4499", "#661100",
  "#6699CC", "#AA4466", "#77AADD", "#44BB99", "#EE8866"
)

colors_warm <- c(
  "#B56576", "#E56B6F", "#EAAC8B", "#6D597A", "#355070",
  "#CB997E", "#D4A373", "#FFB4A2", "#9C6644", "#7F5539",
  "#B5838D", "#E5989B", "#F6BD60", "#F28482", "#84A59D",
  "#F7A072", "#A44A3F", "#5C374C", "#3D405B", "#81B29A",
  "#E07A5F", "#F2CC8F", "#C97B84", "#A26769", "#7D4F50",
  "#D08C60", "#B08968", "#DDA15E", "#9A8C98", "#C9ADA7"
)

colors_fresh <- c(
  "#2A9D8F", "#52B788", "#84CC16", "#F4A261", "#457B9D",
  "#95D5B2", "#74C69D", "#40916C", "#1B4332", "#A7C957",
  "#6A994E", "#BC4749", "#386641", "#A8DADC", "#43AA8B",
  "#90BE6D", "#F9C74F", "#577590", "#4D908E", "#277DA1",
  "#7CB518", "#55A630", "#2D6A4F", "#D9ED92", "#99D98C",
  "#B7E4C7", "#168AAD", "#34A0A4", "#76C893", "#B5E48C"
)

colors_pastel <- c(
  "#A8DADC", "#B8E0D2", "#E9C46A", "#D4A373", "#CDB4DB",
  "#FFC8DD", "#BDE0FE", "#CFE1B9", "#F1C0E8", "#B9FBC0",
  "#FFAFCC", "#A2D2FF", "#D9ED92", "#E4C1F9", "#D0F4DE",
  "#FDE2E4", "#FAD2E1", "#E2ECE9", "#DFE7FD", "#EAE4E9",
  "#CDDAF4", "#F6D6AD", "#DDBDD5", "#BEE1E6", "#F0EFEB",
  "#D9D9D9", "#B8C0DD", "#C7CEEA", "#F8EDEB", "#E3F2FD"
)

colors_nordic <- c(
  "#2B6CB0", "#38A3A5", "#7BC8A4", "#F4A261", "#6C5CE7",
  "#277DA1", "#4D908E", "#43AA8B", "#90BE6D", "#577590",
  "#4EA8DE", "#48BFE3", "#56CFE1", "#64DFDF", "#72EFDD",
  "#80FFDB", "#5390D9", "#5E60CE", "#6930C3", "#7400B8",
  "#89C2D9", "#61A5C2", "#468FAF", "#2C7DA0", "#014F86",
  "#8E9AAF", "#CBC0D3", "#EFD3D7", "#FEEAFA", "#DEE2FF"
)

colors_sunset <- c(
  "#8E6C8A", "#E64B35", "#4DBBD5", "#00A087", "#3C5488",
  "#F39B7F", "#8491B4", "#91D1C2", "#7E6148", "#B09C85",
  "#DC0000", "#7E6148", "#B09C85", "#3C5488", "#00A087",
  "#4DBBD5", "#E64B35", "#8491B4", "#91D1C2", "#F39B7F",
  "#5F559B", "#DF8F44", "#998EC3", "#F1A340", "#998EC3",
  "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3", "#A6D854"
)

colors_urban <- c(
  "#5B8E7D", "#C06C84", "#355C7D", "#F67280", "#F8B195",
  "#6C5B7B", "#99B898", "#FECEAB", "#E84A5F", "#2A363B",
  "#4E6E81", "#D17B88", "#7AA095", "#E59866", "#7D5A50",
  "#8E7DBE", "#66A182", "#C44536", "#EDDDD4", "#197278",
  "#283D3B", "#8D6A9F", "#41B3A3", "#E27D60", "#85DCB0",
  "#6B5B95", "#88B04B", "#F7CAC9", "#92A8D1", "#955251"
)

colors_earth <- c(
  "#D1495B", "#EDAe49", "#66A182", "#2E4057", "#8D6A9F",
  "#F4A261", "#E76F51", "#F28482", "#84A59D", "#6D597A",
  "#B56576", "#EAAC8B", "#355070", "#43AA8B", "#F9C74F",
  "#577590", "#F94144", "#F3722C", "#F8961E", "#90BE6D",
  "#4D908E", "#277DA1", "#CDB4DB", "#FFC8DD", "#BDE0FE",
  "#A8DADC", "#B8E0D2", "#E9C46A", "#D4A373", "#C97B84"
)

get_base_color_scheme <- function(scheme = NULL) {
  scheme <- scheme %||% Sys.getenv("SCFLOW_COLOR_SCHEME", "soft")
  switch(tolower(scheme),
    "soft_academic" = colors_dark,
    "professional_contrast" = colors_pub,
    "publication_classic" = colors_soft,
    "warm_story" = colors_warm,
    "fresh_nature" = colors_fresh,
    "pastel_muted" = colors_pastel,
    "nordic_mist" = colors_nordic,
    "sunset_pop" = colors_sunset,
    "urban_ink" = colors_urban,
    "earth_clay" = colors_earth,
    "dark" = colors_dark,
    "pub" = colors_pub,
    "soft" = colors_soft,
    colors_soft
  )
}

hex_to_lab <- function(colors) {
  rgb <- t(grDevices::col2rgb(colors) / 255)
  grDevices::convertColor(rgb, from = "sRGB", to = "Lab", scale.in = 1)
}

select_distinct_colors <- function(colors, n) {
  colors <- unique(colors)
  if (n >= length(colors)) {
    return(colors)
  }

  lab <- hex_to_lab(colors)
  selected <- integer(n)
  center <- matrix(colMeans(lab), nrow(lab), ncol(lab), byrow = TRUE)
  selected[1] <- which.max(rowSums((lab - center)^2))

  for (i in 2:n) {
    remaining <- setdiff(seq_len(nrow(lab)), selected[seq_len(i - 1)])
    min_dist <- vapply(remaining, function(idx) {
      ref <- lab[selected[seq_len(i - 1)], , drop = FALSE]
      cur <- matrix(lab[idx, ], nrow(ref), ncol(ref), byrow = TRUE)
      min(rowSums((ref - cur)^2))
    }, numeric(1))
    selected[i] <- remaining[which.max(min_dist)]
  }

  colors[selected]
}

get_color_scheme <- function(scheme = NULL, n = NULL) {
  base_colors <- get_base_color_scheme(scheme)
  if (is.null(n) || n <= length(base_colors)) {
    return(select_distinct_colors(base_colors, min(length(base_colors), n %||% length(base_colors))))
  }
  candidates <- c(
    base_colors,
    grDevices::colorRampPalette(base_colors, space = "Lab")(max(n * 6, length(base_colors) * 6))
  )
  select_distinct_colors(candidates, n)
}

sc_colors <- get_color_scheme(n = 128)

set_color_scheme <- function(scheme) {
  sc_colors <<- get_color_scheme(scheme, n = 128)
}

sc_theme <- theme_classic(base_size = 13, base_family = if (nzchar(sc_base_family)) sc_base_family else "sans") +
  theme(
    text = element_text(family = if (nzchar(sc_base_family)) sc_base_family else "sans"),
    plot.title = element_text(
      hjust = 0.5,
      size = 15,
      face = "bold",
      margin = margin(b = 10)
    ),
    plot.subtitle = element_text(
      hjust = 0.5,
      size = 11,
      color = "grey40"
    ),
    axis.title = element_text(size = 12, face = "plain"),
    axis.text = element_text(size = 10, color = "grey30"),
    axis.line = element_line(color = "grey60", linewidth = 0.5),
    legend.position = "right",
    legend.text = element_text(size = 9),
    legend.title = element_text(size = 10, face = "bold"),
    legend.background = element_rect(fill = "transparent"),
    panel.grid.major = element_blank(),
    panel.grid.minor = element_blank(),
    plot.margin = margin(10, 15, 10, 10)
  )

save_svg_plot <- function(plot_obj, svg_path, width, height, bg = "white") {
  svg_ok <- FALSE
  tryCatch({
    ggsave(svg_path, plot = plot_obj, width = width, height = height, bg = bg, device = "svg")
    svg_ok <- isTRUE(file.exists(svg_path))
  }, error = function(e) {
    message(sprintf("[plot_utils] SVG export skipped: %s", conditionMessage(e)))
  })
  invisible(svg_ok)
}

save_plot <- function(plot_obj, name, output_dir,
                      width = 8, height = 6, dpi = 300, limitsize = TRUE) {
  png_path <- file.path(output_dir, paste0(name, ".png"))
  pdf_path <- file.path(output_dir, paste0(name, ".pdf"))
  svg_path <- file.path(output_dir, paste0(name, ".svg"))

  png_ok <- FALSE
  pdf_ok <- FALSE
  svg_ok <- FALSE

  if (identical(Sys.info()[["sysname"]], "Darwin") && nzchar(sc_base_family)) {
    tryCatch({
      grDevices::png(filename = png_path, width = width, height = height, units = "in", res = dpi, type = "quartz", family = sc_base_family, bg = "white")
      print(plot_obj)
      dev.off()
      png_ok <- isTRUE(file.exists(png_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] PNG export failed: %s", conditionMessage(e)))
      try(dev.off(), silent = TRUE)
    })

    tryCatch({
      grDevices::quartz(file = pdf_path, type = "pdf", width = width, height = height, family = sc_base_family)
      print(plot_obj)
      dev.off()
      pdf_ok <- isTRUE(file.exists(pdf_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] quartz PDF failed, fallback to pdf(): %s", conditionMessage(e)))
      try(dev.off(), silent = TRUE)
      tryCatch({
        grDevices::pdf(pdf_path, width = width, height = height, family = if (nzchar(sc_base_family)) sc_base_family else "sans")
        print(plot_obj)
        dev.off()
        pdf_ok <- isTRUE(file.exists(pdf_path))
      }, error = function(e2) {
        message(sprintf("[plot_utils] PDF export failed: %s", conditionMessage(e2)))
        try(dev.off(), silent = TRUE)
      })
    })
  } else {
    tryCatch({
      ggsave(png_path, plot = plot_obj, width = width, height = height, dpi = dpi, bg = "white", limitsize = limitsize)
      png_ok <- isTRUE(file.exists(png_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] PNG export failed: %s", conditionMessage(e)))
    })

    tryCatch({
      ggsave(pdf_path, plot = plot_obj, width = width, height = height, device = cairo_pdf, bg = "white", family = if (nzchar(sc_base_family)) sc_base_family else "sans", limitsize = limitsize)
      pdf_ok <- isTRUE(file.exists(pdf_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] cairo PDF failed, fallback to pdf(): %s", conditionMessage(e)))
      tryCatch({
        grDevices::pdf(pdf_path, width = width, height = height, family = if (nzchar(sc_base_family)) sc_base_family else "sans")
        print(plot_obj)
        dev.off()
        pdf_ok <- isTRUE(file.exists(pdf_path))
      }, error = function(e2) {
        message(sprintf("[plot_utils] PDF export failed: %s", conditionMessage(e2)))
        try(dev.off(), silent = TRUE)
      })
    })
  }

  svg_ok <- save_svg_plot(plot_obj, svg_path, width = width, height = height, bg = "white")

  sidecar_csv <- file.path(output_dir, paste0(name, "_plot_files.csv"))
  tryCatch({
    write.csv(data.frame(
      plot_name = name,
      png_file = if (png_ok) basename(png_path) else "",
      pdf_file = if (pdf_ok) basename(pdf_path) else "",
      svg_file = if (svg_ok) basename(svg_path) else "",
      width_in = width,
      height_in = height,
      dpi = dpi,
      stringsAsFactors = FALSE
    ), sidecar_csv, row.names = FALSE)
  }, error = function(e) {
    message(sprintf("[plot_utils] plot sidecar CSV failed: %s", conditionMessage(e)))
  })

  if (png_ok) cat(sprintf("##PLOT_SAVED:%s\n", png_path))
  if (pdf_ok) cat(sprintf("##PLOT_SAVED:%s\n", pdf_path))
  if (svg_ok) cat(sprintf("##PLOT_SAVED:%s\n", svg_path))
  if (!(png_ok || pdf_ok || svg_ok)) {
    stop(sprintf("Failed to export plot '%s' in PNG/PDF/SVG on this system.", name))
  }

  if (png_ok) return(png_path)
  if (pdf_ok) return(pdf_path)
  svg_path
}

save_base_plot <- function(expr, name, output_dir,
                           width = 8, height = 6, dpi = 300) {
  png_path <- file.path(output_dir, paste0(name, ".png"))
  pdf_path <- file.path(output_dir, paste0(name, ".pdf"))
  svg_path <- file.path(output_dir, paste0(name, ".svg"))

  png_ok <- FALSE
  pdf_ok <- FALSE
  svg_ok <- FALSE

  if (identical(Sys.info()[["sysname"]], "Darwin") && nzchar(sc_base_family)) {
    tryCatch({
      grDevices::png(png_path, width = width, height = height, units = "in", res = dpi, type = "quartz", family = sc_base_family, bg = "white")
      eval(expr)
      dev.off()
      png_ok <- isTRUE(file.exists(png_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] base PNG export failed: %s", conditionMessage(e)))
      try(dev.off(), silent = TRUE)
    })

    tryCatch({
      grDevices::quartz(file = pdf_path, type = "pdf", width = width, height = height, family = sc_base_family)
      eval(expr)
      dev.off()
      pdf_ok <- isTRUE(file.exists(pdf_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] base quartz PDF failed, fallback to pdf(): %s", conditionMessage(e)))
      try(dev.off(), silent = TRUE)
      tryCatch({
        grDevices::pdf(pdf_path, width = width, height = height, family = if (nzchar(sc_base_family)) sc_base_family else "sans")
        eval(expr)
        dev.off()
        pdf_ok <- isTRUE(file.exists(pdf_path))
      }, error = function(e2) {
        message(sprintf("[plot_utils] base PDF export failed: %s", conditionMessage(e2)))
        try(dev.off(), silent = TRUE)
      })
    })
  } else {
    tryCatch({
      grDevices::png(png_path, width = width, height = height, units = "in", res = dpi, bg = "white")
      eval(expr)
      dev.off()
      png_ok <- isTRUE(file.exists(png_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] base PNG export failed: %s", conditionMessage(e)))
      try(dev.off(), silent = TRUE)
    })

    tryCatch({
      cairo_pdf(pdf_path, width = width, height = height, family = if (nzchar(sc_base_family)) sc_base_family else "sans", bg = "white")
      eval(expr)
      dev.off()
      pdf_ok <- isTRUE(file.exists(pdf_path))
    }, error = function(e) {
      message(sprintf("[plot_utils] base cairo PDF failed, fallback to pdf(): %s", conditionMessage(e)))
      try(dev.off(), silent = TRUE)
      tryCatch({
        grDevices::pdf(pdf_path, width = width, height = height, family = if (nzchar(sc_base_family)) sc_base_family else "sans")
        eval(expr)
        dev.off()
        pdf_ok <- isTRUE(file.exists(pdf_path))
      }, error = function(e2) {
        message(sprintf("[plot_utils] base PDF export failed: %s", conditionMessage(e2)))
        try(dev.off(), silent = TRUE)
      })
    })
  }

  tryCatch({
    svg(svg_path, width = width, height = height, family = if (nzchar(sc_base_family)) sc_base_family else "sans", bg = "white")
    eval(expr)
    dev.off()
    svg_ok <- isTRUE(file.exists(svg_path))
  }, error = function(e) {
    message(sprintf("[plot_utils] base SVG export skipped: %s", conditionMessage(e)))
    try(dev.off(), silent = TRUE)
  })

  if (png_ok) cat(sprintf("##PLOT_SAVED:%s\n", png_path))
  if (pdf_ok) cat(sprintf("##PLOT_SAVED:%s\n", pdf_path))
  if (svg_ok) cat(sprintf("##PLOT_SAVED:%s\n", svg_path))
  if (!(png_ok || pdf_ok || svg_ok)) {
    stop(sprintf("Failed to export base plot '%s' on this system.", name))
  }

  if (png_ok) return(png_path)
  if (pdf_ok) return(pdf_path)
  svg_path
}

report_progress <- function(percent, message) {
  cat(sprintf("##PROGRESS:%d:%s\n", as.integer(percent), message))
  flush.console()
}
