import { useState } from "react";
import axios from "axios";
import api from "../services/api";

function Register({ onRegistered, onLoginClick }) {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleRegister = async (event) => {
        event.preventDefault();
        setError("");

        if (!email.trim()) {
            setError("Please enter your email.");
            return;
        }

        if (password.length < 6) {
            setError("Password must be at least 6 characters.");
            return;
        }

        try {
            setLoading(true);

            const response = await api.post(
                "/register",
                {
                    email: email,
                    password: password,
                }
            );

            console.log("Registration successful:", response.data);
            onRegistered();
        } catch (error) {
            console.error("Registration error:", error);
            setError(
                error.response?.data?.detail || "Registration failed."
            );
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-docket-bg text-docket-text flex items-center justify-center p-6 font-sans">
            <div className="w-full max-w-md">
                {/* Branding */}
                <div className="text-center mb-8">
                    <p className="text-[11px] tracking-[0.2em] text-docket-muted uppercase mb-1">
                        Legal RAG Assistant
                    </p>
                    <h1 className="font-serif text-3xl text-docket-heading">
                        Create Account
                    </h1>
                </div>

                {/* Card */}
                <div className="bg-docket-card border border-docket-border rounded-xl p-8">
                    <p className="text-docket-subtext-muted text-sm mb-6">
                        Register to start using the Legal RAG Assistant.
                    </p>

                    <form onSubmit={handleRegister}>
                        <label className="block text-xs tracking-wide text-docket-subtext uppercase mb-2">
                            Email
                        </label>

                        <input
                            type="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            placeholder="you@example.com"
                            className="w-full bg-docket-bg border border-docket-border rounded-lg p-3 mb-5 text-docket-text placeholder:text-docket-placeholder focus:outline-none focus:border-docket-accent transition-colors"
                        />

                        <label className="block text-xs tracking-wide text-docket-subtext uppercase mb-2">
                            Password
                        </label>

                        <input
                            type="password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            placeholder="At least 6 characters"
                            className="w-full bg-docket-bg border border-docket-border rounded-lg p-3 mb-5 text-docket-text placeholder:text-docket-placeholder focus:outline-none focus:border-docket-accent transition-colors"
                        />

                        {error && (
                            <p className="text-docket-danger text-sm mb-4 border-l-2 border-docket-danger pl-3">
                                {error}
                            </p>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-docket-accent text-docket-bg font-medium hover:bg-docket-accent-hover disabled:bg-docket-border disabled:text-docket-muted px-5 py-3 rounded-lg transition-colors cursor-pointer"
                        >
                            {loading ? "Creating account..." : "Create Account"}
                        </button>
                    </form>

                    <div className="mt-6 pt-5 border-t border-docket-border text-center">
                        <p className="text-docket-muted text-sm">
                            Already have an account?
                            <button
                                onClick={onLoginClick}
                                className="ml-2 text-docket-accent hover:text-docket-accent-hover transition-colors cursor-pointer"
                            >
                                Login
                            </button>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Register;