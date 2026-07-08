import React from 'react';

/**
 * Brand logo: the Pay Per Project icon image + wordmark.
 * The image lives in /public/logo.png so it is served from the site root.
 *
 * Wordmark style: "PAY PER" on top (white), "PROJECT" below in a
 * blue→purple gradient, uppercase and bold.
 *
 * Props:
 *  - className: extra classes for the wrapper
 *  - imgClassName: size classes for the logo image (default h-10 w-10)
 *  - showText: whether to render the wordmark (default true)
 *  - textSizeClassName: font-size class for the wordmark (default text-lg)
 */
const Logo = ({
  className = '',
  imgClassName = 'h-10 w-10',
  showText = true,
  textSizeClassName = 'text-lg',
}) => {
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <img
        src="/logo.png"
        alt="Pay Per Project logo"
        className={`${imgClassName} rounded-md object-contain shrink-0`}
      />
      {showText && (
        <span className={`font-heading font-extrabold uppercase leading-[1.05] tracking-tight ${textSizeClassName}`}>
          <span className="block text-white">
            Pay <span className="text-white/70">Per</span>
          </span>
          <span className="block bg-gradient-to-r from-blue-500 to-purple-600 bg-clip-text text-transparent">
            Project
          </span>
        </span>
      )}
    </span>
  );
};

export default Logo;
