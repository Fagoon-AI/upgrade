import React from "react";
import Link from "next/link";

import { ReactNode } from "react";

const PolicyLayout = ({ children }: { children: ReactNode }) => {
  return (
    <main className="min-h-screen py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-200">
      <nav className="max-w-4xl mx-auto mb-8">
        <Link
          href="/chat"
          className="inline-flex items-center text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors duration-200"
        >
          <svg
            className="w-4 h-4 mr-2"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path d="M15 19l-7-7 7-7" />
          </svg>
          Back to Home
        </Link>
      </nav>
      <div className="max-w-4xl mx-auto">
        <div className="bg-white dark:bg-gray-800 shadow-xl rounded-2xl border border-gray-100 dark:border-gray-700 backdrop-blur-sm">
          <div className="p-8 md:p-12">{children}</div>
        </div>
      </div>
      <footer className="max-w-4xl mx-auto mt-8 text-center text-sm text-gray-600 dark:text-gray-400">
        <div className="flex justify-center space-x-6">
          <Link
            href="/privacy-policy"
            className="hover:text-gray-900 dark:hover:text-white transition-colors duration-200"
          >
            Privacy Policy
          </Link>
          <Link
            href="/terms-and-conditions"
            className="hover:text-gray-900 dark:hover:text-white transition-colors duration-200"
          >
            Terms & Conditions
          </Link>
        </div>
      </footer>
    </main>
  );
};

const SectionHeader = ({ children }: { children: ReactNode }) => (
  <h2 className="text-2xl font-bold text-gray-900 dark:text-white mt-12 mb-6 pb-2 border-b border-gray-200 dark:border-gray-700">
    {children}
  </h2>
);

const ListItem = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <li className="flex gap-3">
    <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-blue-600 dark:bg-blue-400 mt-2.5" />
    <div>
      {title && (
        <strong className="text-gray-900 dark:text-white">{title}</strong>
      )}{" "}
      {children}
    </div>
  </li>
);

export function PrivacyPolicy() {
  return (
    <PolicyLayout>
      <div className="prose dark:prose-invert max-w-none">
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4 tracking-tight">
            Privacy Policy
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Last Updated: November 2024
          </p>
        </div>

        <SectionHeader>1. Introduction</SectionHeader>
        <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
          Welcome to{" "}
          <em className="text-blue-600 dark:text-blue-400 font-medium not-italic">
            fagoon.tech
          </em>
          . This Privacy Policy explains how we collect, use, disclose, and
          safeguard your information when you use our platform, including
          services that utilize conversational AI and document-based agent
          features.
        </p>

        <SectionHeader>2. Information Collection</SectionHeader>
        <ul className="space-y-4 text-gray-700 dark:text-gray-300">
          <ListItem title="Personal Information:">
            When you sign up, we collect details such as your name, email, and
            contact information.
          </ListItem>
          <ListItem title="Document Data:">
            If you upload PDFs or other documents for processing, we may
            temporarily store this data to generate responses or interactions.
          </ListItem>
          <ListItem title="Usage Data:">
            We collect information on how you use our platform, such as
            interactions with AI tools, to improve service quality and tailor
            user experiences.
          </ListItem>
          <ListItem title="Cookies and Tracking:">
            We use cookies to enhance your browsing experience and gather
            anonymous analytical data on user interactions.
          </ListItem>
        </ul>

        <SectionHeader>3. Use of Information</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  We use your information for purposes including:
</p>
<ul className="space-y-4 text-gray-700 dark:text-gray-300">
  <ListItem title="Platform Services:">
    Providing, personalizing, and maintaining the platform.
  </ListItem>
  <ListItem title="Improvement of AI Services:">
    Improving AI response accuracy and optimizing service features.
  </ListItem>
  <ListItem title="Marketing and Communications:">
    Informing you of updates, promotions, and relevant content if consented.
  </ListItem>
  <ListItem title="Quality Control:">
    Processing feedback to improve service quality.
  </ListItem>
</ul>

<SectionHeader>4. Information Sharing</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  Your data will not be sold or rented. We may share information:
</p>
<ul className="space-y-4 text-gray-700 dark:text-gray-300">
  <ListItem title="With Third-Party Service Providers:">
    For platform hosting, data analysis, or marketing, ensuring third parties comply with our privacy standards.
  </ListItem>
  <ListItem title="For Legal Reasons:">
    If required by law or to protect the rights, property, or safety of Fagoon AI and its users.
  </ListItem>
</ul>

<SectionHeader>5. Data Security</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  We prioritize your data security. We employ encryption and access control methods to protect your personal data. However, no method of data transmission over the internet is 100% secure, so we cannot guarantee absolute security.
</p>

<SectionHeader>6. User Rights</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  As a user, you have the right to:
</p>
<ul className="space-y-4 text-gray-700 dark:text-gray-300">
  <ListItem title="Access:">
    View the personal data we have about you.
  </ListItem>
  <ListItem title="Rectify:">
    Correct any inaccurate data.
  </ListItem>
  <ListItem title="Erase:">
    Request deletion of your data where legally applicable.
  </ListItem>
  <ListItem title="Opt-out:">
    Decline certain uses of data, such as for marketing.
  </ListItem>
</ul>


        <SectionHeader>7. Contact Us</SectionHeader>
        <p className="text-gray-700 dark:text-gray-300">
          For privacy concerns or requests, please contact us at:{" "}
          <a
            href="mailto:connect@fagoondigital.com"
            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors duration-200"
          >
            connect@fagoondigital.com
          </a>
        </p>
      </div>
    </PolicyLayout>
  );
}

export function TermsAndConditions() {
  return (
    <PolicyLayout>
      <div className="prose dark:prose-invert max-w-none">
        <div className="mb-12 text-center">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4 tracking-tight">
            Terms and Conditions
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Last Updated: November 2024
          </p>
        </div>

        <SectionHeader>1. Acceptance of Terms</SectionHeader>
        <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
          By using{" "}
          <em className="text-blue-600 dark:text-blue-400 font-medium not-italic">
            fagoon.tech
          </em>
          , you agree to be bound by these Terms and Conditions. If you do not
          agree, please refrain from using our platform.
        </p>

        <SectionHeader>2. Services Provided</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  fagoon.tech offers AI-powered tools including conversational agents and document processing features. Our platform allows users to upload PDF files and interact with AI agents capable of extracting and analyzing content.
</p>

<SectionHeader>3. User Responsibilities</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  Users are expected to adhere to the following responsibilities:
</p>
<ul className="space-y-4 text-gray-700 dark:text-gray-300">
  <ListItem title="Compliance with Laws:">
    Users must comply with all applicable Nepalese laws and regulations when using the platform.
  </ListItem>
  <ListItem title="Prohibited Conduct:">
    Users must not misuse the platform to upload malicious content, infringe on intellectual property rights, or engage in harmful activities.
  </ListItem>
  <ListItem title="Content Accuracy:">
    Users are responsible for the accuracy and legality of the documents uploaded.
  </ListItem>
</ul>

<SectionHeader>4. Intellectual Property Rights</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  All content, software, and features available on fagoon.tech are the intellectual property of Fagoon AI. Users are granted a limited, non-transferable license to use these features for personal or internal business purposes. Unauthorized copying or distribution is prohibited.
</p>

<SectionHeader>5. Limitation of Liability</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  fagoon.tech is provided “as-is.” Fagoon AI does not warrant uninterrupted service or error-free operation. We are not liable for any direct, indirect, or consequential damages arising from the use of our platform.
</p>

<SectionHeader>6. Modifications to Terms</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  We reserve the right to modify these terms at any time. Changes will be posted, and continued use of the platform indicates acceptance of updated terms.
</p>

<SectionHeader>7. Governing Law</SectionHeader>
<p className="text-gray-700 dark:text-gray-300 leading-relaxed">
  These Terms and Conditions are governed by the laws of Nepal. Any disputes arising from the use of our platform will be subject to the jurisdiction of Nepalese courts.
</p>


        <SectionHeader>8. Contact Us</SectionHeader>
        <p className="text-gray-700 dark:text-gray-300">
          For questions about these Terms, contact us at:{" "}
          <a
            href="mailto:connect@fagoondigital.com"
            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors duration-200"
          >
            connect@fagoondigital.com
          </a>
        </p>
      </div>
    </PolicyLayout>
  );
}
