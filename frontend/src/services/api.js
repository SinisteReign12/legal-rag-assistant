import axios from "axios";

const API_URL = import.meta.env.VITE_BACKEND_URL;

const api = axios.create({
    baseURL: API_URL,
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem("token");

    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
});


api.interceptors.response.use(
    (response) => response,

    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem("token");
            localStorage.removeItem("user_id");
            localStorage.removeItem("email");
            localStorage.removeItem("conversationId");

            window.location.replace("/");
        }

        return Promise.reject(error);
    }
);


export async function deleteConversation(conversationId) {
    const response = await api.delete(
        `/conversations/${conversationId}`
    );

    return response.data;
}

export async function createConversation(title) {
    const response = await api.post(
        "/conversations",
        { title }
    );

    return response.data;
}

export async function updateConversation(conversationId, title) {
    const response = await api.patch(
        `/conversations/${conversationId}`,
        { title }
    );

    return response.data;
}

export async function uploadPDF(conversationId, file) {
    const formData = new FormData();

    formData.append("file", file);

    const response = await api.post(
        `/conversations/${conversationId}/upload`,
        formData
    );

    return response.data;
}

export async function askQuestion(conversationId, query) {
    const response = await api.post(
        "/ask",
        {
            conversation_id: conversationId,
            query: query,
        }
    );

    return response.data;
}

export async function getMessages(conversationId) {
    const response = await api.get(
        `/conversations/${conversationId}/messages`
    );

    return response.data;
}

export async function getConversations() {
    const response = await api.get(
        "/conversations"
    );

    return response.data;
}

export async function removePDF(conversationId) {
    const response = await api.delete(
        `/conversations/${conversationId}/document`
    );

    return response.data;
}

export async function getDocument(conversationId) {
    const response = await api.get(
        `/conversations/${conversationId}/document`
    );

    return response.data;
}
