plugins: [
    require('@tailwindcss/line-clamp'),
]

module.exports = {
    content: [
        "./templates/**/*.html"
    ],
    theme: {
        extend: {}
    },
    plugins: [
        require("@tailwindcss/typography")
    ]
}

modules: {
    toolbar: [
        [{ list: "ordered" }, { list: "bullet" }]
    ]
}